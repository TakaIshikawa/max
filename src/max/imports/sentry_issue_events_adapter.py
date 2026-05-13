"""Sentry issue events import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
SENTRY_API = "https://sentry.io/api/0"


class SentryIssueEventsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        auth_token: str | None = None,
        base_url: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = auth_token if auth_token is not None else (token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("auth_token")) or os.getenv("SENTRY_AUTH_TOKEN")))
        self.api_url = (api_url or base_url or _optional(self._config.get("api_url")) or _optional(self._config.get("base_url")) or SENTRY_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "sentry_issue_events_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def issue_ids(self) -> list[str]:
        return _strings(self._config.get("issue_ids") or self._config.get("issue_id") or self._config.get("issues"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.issue_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for issue_id in self.issue_ids:
                if len(signals) >= limit:
                    break
                events = await self._fetch_issue_events(client, issue_id=issue_id, limit=limit - len(signals))
                signals.extend(_event_signal(event, issue_id=issue_id, adapter_name=self.name) for event in events)
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_issue_events(self, client: httpx.AsyncClient, *, issue_id: str, limit: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(events) < limit:
            page_size = min(self.page_size, limit - len(events))
            page, cursor = await self._fetch_page(client, issue_id=issue_id, cursor=cursor, page_size=page_size)
            if not page:
                break
            events.extend(page[: limit - len(events)])
            if not cursor:
                break
        return events[:limit]

    async def _fetch_page(self, client: httpx.AsyncClient, *, issue_id: str, cursor: str | None, page_size: int) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"per_page": page_size}
        if cursor:
            params["cursor"] = cursor
        try:
            response = await client.get(
                f"{self.api_url}/issues/{issue_id}/events/",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-sentry-issue-events-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Sentry issue events fetch failed for issue %s", issue_id, exc_info=True)
            return [], None
        events = _events(body)
        return events, _next_cursor(response, body)


SentryIssueEventAdapter = SentryIssueEventsAdapter


def _event_signal(event: dict[str, Any], *, issue_id: str, adapter_name: str) -> Signal:
    event_id = _text(event.get("id") or event.get("eventID") or event.get("event_id"))
    culprit = _optional(event.get("culprit"))
    platform = _optional(event.get("platform"))
    release = _release(event)
    environment = _environment(event)
    title = _optional(event.get("title") or event.get("message")) or f"Sentry issue {issue_id} event"
    return Signal(
        id=f"sentry-issue-event:{issue_id}:{event_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Sentry issue {issue_id} event {event_id or 'unknown'}",
        content=_content(title=title, culprit=culprit, platform=platform, release=release, environment=environment),
        url=_optional(event.get("web_url") or event.get("webUrl") or event.get("url")) or "",
        author=None,
        published_at=_parse_dt(event.get("dateCreated") or event.get("datetime") or event.get("timestamp")),
        tags=sorted({"sentry", "issue-event", platform or "", release or "", environment or ""} | set(_tag_values(event)))[:10],
        credibility=0.7,
        metadata={
            "signal_role": "failure_data",
            "sentry_issue_id": issue_id,
            "sentry_event_id": event_id,
            "culprit": culprit,
            "platform": platform,
            "release": release,
            "environment": environment,
            "tags": _tags(event),
            "message": event.get("message"),
            "title": title,
            "date_created": event.get("dateCreated") or event.get("datetime") or event.get("timestamp"),
            "raw": event,
        },
    )


def _events(body: object) -> list[dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        results = body.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    return []


def _next_cursor(response: httpx.Response, body: object) -> str | None:
    next_link = response.links.get("next") if response.links else None
    if next_link and _text(next_link.get("results")).lower() != "false":
        cursor = _optional(next_link.get("cursor"))
        if cursor:
            return cursor
        next_url = _optional(next_link.get("url"))
        if next_url:
            return _optional(str(httpx.URL(next_url).params.get("cursor")))
    if not isinstance(body, dict):
        return None
    cursor = body.get("cursor") if isinstance(body.get("cursor"), dict) else {}
    if cursor and cursor.get("hasNext"):
        return _optional(cursor.get("next") or cursor.get("nextCursor"))
    pagination = body.get("pagination") if isinstance(body.get("pagination"), dict) else {}
    if pagination and pagination.get("hasNext"):
        return _optional(pagination.get("next") or pagination.get("nextCursor"))
    return None


def _content(*, title: str, culprit: str | None, platform: str | None, release: str | None, environment: str | None) -> str:
    parts = [title]
    if culprit:
        parts.append(f"culprit {culprit}")
    if platform:
        parts.append(f"platform {platform}")
    if release:
        parts.append(f"release {release}")
    if environment:
        parts.append(f"environment {environment}")
    return "; ".join(parts)[:1000]


def _release(event: dict[str, Any]) -> str | None:
    release = event.get("release")
    if isinstance(release, dict):
        return _optional(release.get("version") or release.get("shortVersion") or release.get("id"))
    return _optional(release or _tag_lookup(event, "release"))


def _environment(event: dict[str, Any]) -> str | None:
    return _optional(event.get("environment") or _tag_lookup(event, "environment"))


def _tag_lookup(event: dict[str, Any], key: str) -> str | None:
    for tag in _tags(event):
        if tag.get("key") == key:
            return _optional(tag.get("value"))
    return None


def _tag_values(event: dict[str, Any]) -> list[str]:
    return [_text(tag.get("value")) for tag in _tags(event) if _text(tag.get("value"))]


def _tags(event: dict[str, Any]) -> list[dict[str, Any]]:
    tags = event.get("tags")
    if isinstance(tags, list):
        normalized: list[dict[str, Any]] = []
        for tag in tags:
            if isinstance(tag, dict):
                normalized.append(tag)
            elif isinstance(tag, (list, tuple)) and len(tag) >= 2:
                normalized.append({"key": tag[0], "value": tag[1]})
        return normalized
    return []


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
