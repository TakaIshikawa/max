"""Zendesk ticket import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = base_url or _optional(self._config.get("base_url"))
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else os.getenv("ZENDESK_EMAIL")
        self.token = token if token is not None else os.getenv("ZENDESK_API_TOKEN")
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def query(self) -> str | None:
        return _optional(self._config.get("query"))

    @property
    def view_id(self) -> str | None:
        return _optional(self._config.get("view_id"))

    @property
    def page_size(self) -> int:
        value = self._config.get("page_size")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 100

    @property
    def statuses(self) -> list[str]:
        return _strings(self._config.get("statuses"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            tickets: list[dict[str, Any]] = []
            url = self._initial_url()
            params = self._initial_params()
            while url and len(tickets) < limit:
                body = await self._get(client, url=url, params=params)
                page = self._tickets(body)
                tickets.extend(page)
                url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
                params = None
                if not page:
                    break
        finally:
            if close_client:
                await client.aclose()

        allowed_statuses = {status.lower() for status in self.statuses}
        signals: list[Signal] = []
        seen: set[str] = set()
        for ticket in tickets:
            if not isinstance(ticket, dict):
                continue
            ticket_id = _text(ticket.get("id"))
            if not ticket_id or ticket_id in seen:
                continue
            seen.add(ticket_id)
            status = _text(ticket.get("status"))
            if allowed_statuses and status.lower() not in allowed_statuses:
                continue
            signals.append(_ticket_signal(ticket, self.name, self.base_url))
            if len(signals) >= limit:
                break
        return signals

    def _initial_url(self) -> str:
        if self.view_id:
            return f"{self.base_url}/api/v2/views/{self.view_id}/tickets.json"
        return f"{self.base_url}/api/v2/search.json"

    def _initial_params(self) -> dict[str, Any]:
        if self.view_id:
            return {"per_page": self.page_size}
        query = self.query or "type:ticket"
        return {"query": query, "per_page": self.page_size}

    async def _get(self, client: httpx.AsyncClient, *, url: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(url, auth=(f"{self.email}/token", self.token or ""), params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _tickets(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        key = "tickets" if self.view_id else "results"
        value = body.get(key)
        return value if isinstance(value, list) else []


ZendeskTicketAdapter = ZendeskAdapter


def _ticket_signal(ticket: dict[str, Any], adapter_name: str, base_url: str) -> Signal:
    ticket_id = _text(ticket.get("id"))
    url = _text(ticket.get("url")) or (f"{base_url}/agent/tickets/{ticket_id}" if ticket_id else base_url)
    satisfaction = ticket.get("satisfaction_rating") if isinstance(ticket.get("satisfaction_rating"), dict) else {}
    custom_fields = {field.get("id"): field.get("value") for field in ticket.get("custom_fields", []) if isinstance(field, dict)}
    tags = [_text(tag) for tag in ticket.get("tags", []) if _text(tag)]
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(ticket.get("subject")) or ticket_id,
        content=_text(ticket.get("description"))[:1000],
        url=url,
        author=_text(ticket.get("requester_id")) or None,
        published_at=_parse_dt(ticket.get("created_at")),
        tags=sorted({"zendesk", _text(ticket.get("status")), _text(ticket.get("priority")), *tags} - {""})[:10],
        credibility=0.6,
        metadata={
            "zendesk_ticket_id": ticket.get("id"),
            "requester_id": ticket.get("requester_id"),
            "submitter_id": ticket.get("submitter_id"),
            "assignee_id": ticket.get("assignee_id"),
            "status": ticket.get("status"),
            "priority": ticket.get("priority"),
            "tags": tags,
            "custom_fields": custom_fields,
            "created_at": ticket.get("created_at"),
            "updated_at": ticket.get("updated_at"),
            "satisfaction_rating": satisfaction,
        },
    )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
