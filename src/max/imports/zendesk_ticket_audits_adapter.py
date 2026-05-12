"""Zendesk ticket audits import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketAuditsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        oauth_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = base_url or _optional(self._config.get("base_url")) or os.getenv("ZENDESK_BASE_URL")
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.api_token = api_token if api_token is not None else (
            _optional(self._config.get("api_token"))
            or _optional(self._config.get("token"))
            or os.getenv("ZENDESK_API_TOKEN")
        )
        self.oauth_token = oauth_token if oauth_token is not None else (
            _optional(self._config.get("oauth_token")) or os.getenv("ZENDESK_OAUTH_TOKEN")
        )
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_ticket_audits_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def ticket_ids(self) -> list[str]:
        return _strings(self._config.get("ticket_ids") or self._config.get("ticket_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=100)

    @property
    def _has_auth(self) -> bool:
        return bool(self.oauth_token or (self.email and self.api_token))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.ticket_ids and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
            for ticket_id in self.ticket_ids:
                if len(rows) >= limit:
                    break
                audits = await self._fetch_ticket_audits(
                    client,
                    ticket_id=ticket_id,
                    limit=limit - len(rows),
                )
                for audit in audits:
                    events = audit.get("events") if isinstance(audit.get("events"), list) else []
                    for event in events:
                        if isinstance(event, dict):
                            rows.append((ticket_id, audit, event))
                        if len(rows) >= limit:
                            break
                    if len(rows) >= limit:
                        break
            return [_audit_event_signal(ticket_id, audit, event, self.name, self.base_url) for ticket_id, audit, event in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_ticket_audits(
        self,
        client: httpx.AsyncClient,
        *,
        ticket_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        audits: list[dict[str, Any]] = []
        url = f"{self.base_url}/api/v2/tickets/{ticket_id}/audits.json"
        params: dict[str, Any] | None = {"page[size]": min(self.page_size, limit)}
        while url and len(audits) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("audits") if isinstance(body.get("audits"), list) else []
            if not page:
                break
            audits.extend(item for item in page if isinstance(item, dict))
            url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
            params = None
        return audits[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "max-zendesk-ticket-audits-import/1"}
        auth = None
        if self.oauth_token:
            headers["Authorization"] = f"Bearer {self.oauth_token}"
        else:
            auth = (f"{self.email}/token", self.api_token or "")
        try:
            response = await client.get(url, headers=headers, auth=auth, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket audit fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskTicketAuditsAdapter = ZendeskTicketAuditsImportAdapter


def _audit_event_signal(
    ticket_id: str,
    audit: dict[str, Any],
    event: dict[str, Any],
    adapter_name: str,
    base_url: str,
) -> Signal:
    audit_id = _text(audit.get("id"))
    event_id = _text(event.get("id")) or _text(event.get("type")) or _text(audit.get("created_at"))
    event_type = _text(event.get("type")) or "AuditEvent"
    author_id = _optional(audit.get("author_id"))
    return Signal(
        id=f"zendesk-ticket-audit-event:{ticket_id}:{audit_id}:{event_id}",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Zendesk ticket {ticket_id} audit {event_type}",
        content=_event_content(event, event_type)[:1000],
        url=f"{base_url}/agent/tickets/{ticket_id}",
        author=author_id,
        published_at=_parse_dt(audit.get("created_at")),
        tags=sorted({"zendesk", "ticket-audit", event_type.lower()} - {""})[:10],
        credibility=0.65,
        metadata={
            "ticket_id": ticket_id,
            "audit_id": audit.get("id"),
            "event_id": event.get("id"),
            "event_type": event.get("type"),
            "author_id": audit.get("author_id"),
            "via": audit.get("via"),
            "metadata": audit.get("metadata"),
            "created_at": audit.get("created_at"),
            "raw_audit": audit,
            "raw": event,
        },
    )


def _event_content(event: dict[str, Any], event_type: str) -> str:
    field = _optional(event.get("field_name") or event.get("field"))
    previous = _optional(event.get("previous_value"))
    value = _optional(event.get("value"))
    if field and (previous or value):
        return f"{event_type} changed {field} from {previous or 'empty'} to {value or 'empty'}"
    body = _optional(event.get("body") or event.get("plain_body") or event.get("value"))
    if body:
        return body
    return event_type


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
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
