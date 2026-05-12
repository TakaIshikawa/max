"""Jira Service Management request comments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
ATLASSIAN_API = "https://api.atlassian.com"


class JiraServiceManagementRequestCommentsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        cloud_id: str | None = None,
        site_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        bearer_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.cloud_id = cloud_id or _optional(self._config.get("cloud_id"))
        self.site_url = (site_url or _optional(self._config.get("site_url")) or _optional(self._config.get("base_url")) or "").rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("JIRA_EMAIL") or os.getenv("JIRA_USERNAME"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("api_token")))
        self.bearer_token = (
            bearer_token
            if bearer_token is not None
            else (_optional(self._config.get("bearer_token")) or os.getenv("JIRA_SERVICE_MANAGEMENT_TOKEN"))
        )
        self._client = client

    @property
    def name(self) -> str:
        return "jira_service_management_request_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        if self.cloud_id:
            return f"{ATLASSIAN_API}/ex/jira/{self.cloud_id}/rest/servicedeskapi"
        return f"{self.site_url}/rest/servicedeskapi" if self.site_url else ""

    @property
    def request_identifiers(self) -> list[str]:
        value = (
            self._config.get("request_identifiers")
            or self._config.get("request_ids")
            or self._config.get("request_keys")
            or self._config.get("issue_ids")
            or self._config.get("issue_keys")
            or self._config.get("request_id")
            or self._config.get("request_key")
            or self._config.get("issue_id")
            or self._config.get("issue_key")
        )
        return _strings(value)

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=50, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.base_url or not self.request_identifiers or not (self.bearer_token or (self.email and self.token)):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for request_identifier in self.request_identifiers:
                if len(signals) >= limit:
                    break
                comments = await self._fetch_request_comments(
                    client,
                    request_identifier=request_identifier,
                    limit=limit - len(signals),
                )
                for comment in comments:
                    signal = _comment_signal(comment, request_identifier, self.name, self.site_url, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_request_comments(
        self,
        client: httpx.AsyncClient,
        *,
        request_identifier: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        start = 0
        while len(comments) < limit:
            page_limit = min(self.page_size, limit - len(comments))
            body = await self._fetch_page(client, request_identifier=request_identifier, start=start, limit=page_limit)
            values = body.get("values") if isinstance(body.get("values"), list) else []
            if not values:
                break
            comments.extend(item for item in values if isinstance(item, dict))
            if body.get("isLastPage") is True or len(values) < page_limit:
                break
            start = _int(body.get("start"), start) + len(values)
        return comments[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        *,
        request_identifier: str,
        start: int,
        limit: int,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.base_url}/request/{request_identifier}/comment",
                headers=self._headers(),
                auth=self._auth(),
                params={"start": start, "limit": limit},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Jira Service Management request comment fetch failed for %s", request_identifier, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def _auth(self) -> tuple[str, str] | None:
        if self.bearer_token or not (self.email and self.token):
            return None
        return (self.email, self.token)


JiraServiceManagementRequestCommentAdapter = JiraServiceManagementRequestCommentsAdapter


def _comment_signal(
    comment: dict[str, Any],
    request_identifier: str,
    adapter_name: str,
    site_url: str,
    seen: set[str],
) -> Signal | None:
    comment_id = _optional(comment.get("id"))
    if not comment_id:
        return None
    external_id = f"jira-service-management-request-comment:{request_identifier}:{comment_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    author = comment.get("author") if isinstance(comment.get("author"), dict) else {}
    created = _date_field(comment.get("created"))
    body = _body_text(comment.get("body") or comment.get("renderedBody"))
    visibility = _visibility(comment)
    source_url = _source_url(comment, request_identifier, site_url)
    author_name = _optional(author.get("displayName") or author.get("emailAddress") or author.get("name"))

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"{request_identifier} request comment",
        content=body[:1000],
        url=source_url,
        author=author_name,
        published_at=_parse_dt(created),
        tags=sorted({"jira-service-management", "request-comment", visibility} - {""})[:10],
        credibility=0.65,
        metadata={
            "request_identifier": request_identifier,
            "request_key": request_identifier if not request_identifier.isdigit() else None,
            "request_id": request_identifier if request_identifier.isdigit() else None,
            "comment_id": comment_id,
            "visibility": visibility,
            "public": comment.get("public"),
            "author": {
                "account_id": author.get("accountId"),
                "name": author.get("name") or author.get("displayName"),
                "display_name": author.get("displayName"),
                "email": author.get("emailAddress"),
            },
            "body": body,
            "created_at": created,
            "source_url": source_url,
            "links": comment.get("_links") if isinstance(comment.get("_links"), dict) else {},
            "raw": comment,
        },
    )


def _visibility(comment: dict[str, Any]) -> str:
    public = comment.get("public")
    if public is True:
        return "public"
    if public is False:
        return "internal"
    visibility = comment.get("visibility") if isinstance(comment.get("visibility"), dict) else {}
    return _text(visibility.get("type") or visibility.get("value") or comment.get("visibility"))


def _source_url(comment: dict[str, Any], request_identifier: str, site_url: str) -> str:
    links = comment.get("_links") if isinstance(comment.get("_links"), dict) else {}
    for value in (comment.get("webUrl"), comment.get("self"), links.get("web"), links.get("self")):
        url = _link_href(value)
        if url:
            return url
    if site_url and request_identifier:
        return f"{site_url}/browse/{request_identifier}"
    return ""


def _link_href(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("href"))
    return _text(value)


def _body_text(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("value") or value.get("text") or value.get("plainText"))
    return _text(value)


def _date_field(value: object) -> str:
    if isinstance(value, dict):
        return _text(value.get("iso8601") or value.get("jira") or value.get("friendly"))
    return _text(value)


def _parse_dt(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
