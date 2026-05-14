"""PagerDuty incident log entries import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_PAGERDUTY_API_URL = "https://api.pagerduty.com"


class PagerDutyIncidentLogEntriesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_token: str | None = None,
        api_url: str = DEFAULT_PAGERDUTY_API_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_token = api_token if api_token is not None else (
            token or _optional(self._config.get("api_token")) or _optional(self._config.get("token")) or os.getenv("PAGERDUTY_API_TOKEN")
        )
        self.api_url = (_optional(self._config.get("api_url")) or api_url).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "pagerduty_incident_log_entries_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def incident_ids(self) -> list[str]:
        return _strings(self._config.get("incident_ids") or self._config.get("incident_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("limit") or self._config.get("page_size"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.api_token and self.incident_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any]]] = []
            for incident_id in self.incident_ids:
                if len(rows) >= limit:
                    break
                entries = await self._fetch_entries(client, incident_id=incident_id, limit=limit - len(rows))
                if entries is None:
                    return []
                rows.extend((incident_id, entry) for entry in entries)
            return [_entry_signal(incident_id, entry, self.name) for incident_id, entry in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_entries(self, client: httpx.AsyncClient, *, incident_id: str, limit: int) -> list[dict[str, Any]] | None:
        entries: list[dict[str, Any]] = []
        path_or_url = f"/incidents/{incident_id}/log_entries"
        offset = 0
        while len(entries) < limit and path_or_url:
            page_limit = min(self.page_size, limit - len(entries))
            body = await self._get(client, path_or_url, params={"limit": page_limit, "offset": offset})
            if body is None:
                return None
            page = body.get("log_entries") if isinstance(body.get("log_entries"), list) else []
            if not page:
                break
            entries.extend(item for item in page if isinstance(item, dict))
            next_url = _optional(body.get("next"))
            if next_url:
                path_or_url = next_url
                offset = _next_offset(body, offset, page_limit)
                continue
            if not bool(body.get("more")):
                break
            offset = _next_offset(body, offset, page_limit)
        return entries[:limit]

    async def _get(self, client: httpx.AsyncClient, path_or_url: str, *, params: dict[str, Any]) -> dict[str, Any] | None:
        url = path_or_url if path_or_url.startswith(("http://", "https://")) else f"{self.api_url}{path_or_url}"
        try:
            response = await client.get(url, params=params, headers=self._headers())
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("PagerDuty incident log entries fetch failed", exc_info=True)
            return None
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Authorization": f"Token token={self.api_token}",
            "User-Agent": "max-pagerduty-incident-log-entries-import/1",
        }


PagerDutyIncidentLogEntryAdapter = PagerDutyIncidentLogEntriesAdapter


def _entry_signal(incident_id: str, entry: dict[str, Any], adapter_name: str) -> Signal:
    entry_id = _text(entry.get("id")) or _text(entry.get("created_at"))
    agent = entry.get("agent") if isinstance(entry.get("agent"), dict) else {}
    channel = entry.get("channel") if isinstance(entry.get("channel"), dict) else {}
    incident = entry.get("incident") if isinstance(entry.get("incident"), dict) else {}
    entry_type = _text(entry.get("type"))
    summary = _text(entry.get("summary")) or entry_type or f"PagerDuty log entry {entry_id}"
    return Signal(
        id=f"pagerduty-log-entry:{incident_id}:{entry_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=summary,
        content=_content(entry, summary)[:1000],
        url=_text(entry.get("html_url") or entry.get("self") or incident.get("html_url")),
        author=_optional(agent.get("summary") or agent.get("name") or agent.get("email") or agent.get("id")),
        published_at=_parse_dt(entry.get("created_at")),
        tags=sorted({"pagerduty", "incident", "log-entry", entry_type.lower()} - {""})[:10],
        credibility=0.7,
        metadata={
            "pagerduty_log_entry_id": entry.get("id"),
            "pagerduty_incident_id": incident_id,
            "type": entry.get("type"),
            "summary": entry.get("summary"),
            "channel": _entity_summary(channel),
            "agent": _entity_summary(agent),
            "incident": _entity_summary(incident) or {"id": incident_id},
            "created_at": entry.get("created_at"),
            "html_url": entry.get("html_url"),
            "self": entry.get("self"),
            "raw": entry,
        },
    )


def _content(entry: dict[str, Any], summary: str) -> str:
    details = entry.get("details") if isinstance(entry.get("details"), dict) else {}
    detail_text = _optional(details.get("message") or details.get("description") or details.get("note"))
    return f"{summary}. {detail_text}" if detail_text else summary


def _entity_summary(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    return {
        "id": value.get("id"),
        "summary": value.get("summary"),
        "name": value.get("name"),
        "email": value.get("email"),
        "type": value.get("type"),
        "self": value.get("self"),
        "html_url": value.get("html_url"),
    }


def _next_offset(body: dict[str, Any], offset: int, limit: int) -> int:
    try:
        return int(body.get("offset", offset)) + int(body.get("limit", limit))
    except (TypeError, ValueError):
        return offset + limit


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
        value = [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
