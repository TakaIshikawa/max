"""Sentry issue tags import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SENTRY_API = "https://sentry.io/api/0"
DEFAULT_TAG_KEYS = ("environment", "release", "browser", "device", "transaction", "handled")


class SentryIssueTagsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        auth_token: str | None = None,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            auth_token
            if auth_token is not None
            else (
                token
                if token is not None
                else (
                    _optional(self._config.get("auth_token"))
                    or _optional(self._config.get("token"))
                    or os.getenv("SENTRY_AUTH_TOKEN")
                )
            )
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_issue_tags_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def organization_slug(self) -> str | None:
        return _optional(self._config.get("organization_slug") or self._config.get("org_slug") or os.getenv("SENTRY_ORG_SLUG"))

    @property
    def issue_ids(self) -> list[str]:
        return _strings(self._config.get("issue_ids") or self._config.get("issues") or self._config.get("issue_id"))

    @property
    def key_filters(self) -> list[str]:
        configured = _strings(self._config.get("key_filters") or self._config.get("tag_keys") or self._config.get("keys"))
        return configured or list(DEFAULT_TAG_KEYS)

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=25, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.issue_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for issue_id in self.issue_ids:
                if len(signals) >= limit:
                    break
                tags = await self._fetch_issue_tags(client, issue_id=issue_id)
                selected_tags = self._selected_tags(tags)
                for tag in selected_tags:
                    if len(signals) >= limit:
                        break
                    key = _text(tag.get("key") or tag.get("name"))
                    values = await self._fetch_tag_values(
                        client,
                        issue_id=issue_id,
                        key=key,
                        limit=max(1, limit),
                    )
                    signals.append(_tag_signal(tag, values, issue_id=issue_id, adapter_name=self.name, api_url=self.api_url, organization_slug=self.organization_slug))
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_tags(self, client: httpx.AsyncClient, *, issue_id: str) -> list[dict[str, Any]]:
        body = await self._get_list(client, f"{self.api_url}/issues/{issue_id}/tags/", params={"per_page": self.page_size})
        return body

    async def _fetch_tag_values(
        self,
        client: httpx.AsyncClient,
        *,
        issue_id: str,
        key: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(values) < limit:
            params: dict[str, Any] = {"per_page": min(self.page_size, limit - len(values))}
            if cursor:
                params["cursor"] = cursor
            page, cursor = await self._get_list_with_cursor(
                client,
                f"{self.api_url}/issues/{issue_id}/tags/{quote(key, safe='')}/values/",
                params=params,
            )
            if not page:
                break
            values.extend(page[: limit - len(values)])
            if not cursor:
                break
        return values[:limit]

    async def _get_list(self, client: httpx.AsyncClient, url: str, *, params: dict[str, Any]) -> list[dict[str, Any]]:
        page, _cursor = await self._get_list_with_cursor(client, url, params=params)
        return page

    async def _get_list_with_cursor(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], str | None]:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-issue-tags-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry issue tags fetch failed for %s", url, exc_info=True)
            return [], None
        return ([item for item in body if isinstance(item, dict)] if isinstance(body, list) else []), _next_cursor(response)

    def _selected_tags(self, tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {key.lower() for key in self.key_filters}
        selected: list[dict[str, Any]] = []
        for tag in tags:
            key = _text(tag.get("key") or tag.get("name"))
            if key and key.lower() in allowed:
                selected.append(tag)
        return selected


SentryIssueTagsAdapter = SentryIssueTagsImportAdapter


def _tag_signal(
    tag: dict[str, Any],
    values: list[dict[str, Any]],
    *,
    issue_id: str,
    adapter_name: str,
    api_url: str,
    organization_slug: str | None,
) -> Signal:
    key = _text(tag.get("key") or tag.get("name"))
    sorted_values = sorted(values, key=lambda item: _int(item.get("count") or item.get("value_count")), reverse=True)
    top = sorted_values[0] if sorted_values else {}
    top_value = _optional(top.get("value") or top.get("name"))
    value_counts = {
        _text(item.get("value") or item.get("name")): _int(item.get("count") or item.get("value_count"))
        for item in sorted_values
        if _text(item.get("value") or item.get("name"))
    }
    total_values = _int(tag.get("totalValues") or tag.get("total_values") or tag.get("uniqueValues") or len(values))
    query_url = _query_url(api_url, organization_slug, issue_id, key, top_value)
    content = f"{key} clusters issue {issue_id}"
    if top_value:
        content = f"Top {key} value for issue {issue_id}: {top_value} ({value_counts.get(top_value, 0)})"

    return Signal(
        id=f"sentry-issue-tag:{issue_id}:{key}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Sentry issue {issue_id} tag distribution: {key}",
        content=content[:1000],
        url=query_url,
        author=None,
        published_at=_parse_dt(top.get("firstSeen") or top.get("first_seen")),
        tags=sorted({"sentry", "issue-tag", key, _text(top_value)} - {""})[:10],
        credibility=min((sum(value_counts.values()) or total_values) / 1000, 1.0),
        metadata={
            "sentry_issue_id": issue_id,
            "issue_id": issue_id,
            "tag_key": key,
            "top_value": top_value,
            "value_counts": value_counts,
            "total_values": total_values,
            "query_url": query_url,
            "raw_tag": tag,
            "raw_values": values,
        },
    )


def _query_url(api_url: str, organization_slug: str | None, issue_id: str, key: str, value: str | None) -> str:
    if organization_slug:
        host = api_url.split("/api/")[0].rstrip("/")
        query = f"issue.id:{issue_id} {key}:{value}" if value else f"issue.id:{issue_id} has:{key}"
        return f"{host}/organizations/{organization_slug}/issues/?query={quote(query)}"
    return f"{api_url}/issues/{issue_id}/tags/{quote(key, safe='')}/values/"


def _next_cursor(response: httpx.Response) -> str | None:
    next_link = response.links.get("next") if response.links else None
    if not next_link:
        return None
    if _text(next_link.get("results")).lower() == "false":
        return None
    cursor = _optional(next_link.get("cursor"))
    if cursor:
        return cursor
    next_url = _optional(next_link.get("url"))
    if not next_url:
        return None
    return _optional(str(httpx.URL(next_url).params.get("cursor")))


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
