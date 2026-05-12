"""Freshservice ticket import adapter."""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
FRESHSERVICE_API_TEMPLATE = "https://{domain}.freshservice.com"


class FreshserviceTicketsAdapter(SourceAdapter):
    """Fetch Freshservice tickets and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        domain: str | None = None,
        api_key: str | None = None,
        api_url: str | None = None,
        status: str | int | None = None,
        requester_id: str | int | None = None,
        department_id: str | int | None = None,
        page_size: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.domain = (
            domain
            if domain is not None
            else (_optional(self._config.get("domain")) or os.getenv("FRESHSERVICE_DOMAIN"))
        )
        self.api_key = (
            api_key
            if api_key is not None
            else (_optional(self._config.get("api_key")) or os.getenv("FRESHSERVICE_API_KEY"))
        )
        configured_api_url = api_url or _optional(self._config.get("api_url"))
        self.api_url = (configured_api_url or self._domain_api_url()).rstrip("/")
        self.status = status if status is not None else self._config.get("status")
        self.requester_id = (
            requester_id if requester_id is not None else self._config.get("requester_id")
        )
        self.department_id = (
            department_id if department_id is not None else self._config.get("department_id")
        )
        self._page_size = page_size if page_size is not None else self._config.get("page_size")
        self._client = client

    @property
    def name(self) -> str:
        return "freshservice_tickets_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def page_size(self) -> int:
        value = self._page_size
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 30

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.domain and self.api_key):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            tickets = await self._fetch_tickets(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [
            _ticket_signal(ticket, adapter_name=self.name, api_url=self.api_url)
            for ticket in tickets[:limit]
        ]

    async def _fetch_tickets(
        self, client: httpx.AsyncClient, *, limit: int
    ) -> list[dict[str, Any]]:
        tickets: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        while len(tickets) < limit:
            per_page = min(self.page_size, max(1, limit - len(tickets)))
            page_items = await self._get_page(client, page=page, per_page=per_page)
            if not page_items:
                break
            for ticket in page_items:
                if not isinstance(ticket, dict):
                    continue
                ticket_id = _text(ticket.get("id"))
                if not ticket_id or ticket_id in seen:
                    continue
                seen.add(ticket_id)
                tickets.append(ticket)
                if len(tickets) >= limit:
                    break
            if len(page_items) < per_page:
                break
            page += 1
        return tickets

    async def _get_page(
        self, client: httpx.AsyncClient, *, page: int, per_page: int
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if self.status not in (None, ""):
            params["status"] = self.status
        if self.requester_id not in (None, ""):
            params["requester_id"] = self.requester_id
        if self.department_id not in (None, ""):
            params["department_id"] = self.department_id
        try:
            response = await client.get(
                f"{self.api_url}/api/v2/tickets",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Freshservice ticket fetch failed", exc_info=True)
            return []
        if isinstance(body, dict) and isinstance(body.get("tickets"), list):
            return body["tickets"]
        return body if isinstance(body, list) else []

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Basic {_basic_token(self.api_key)}",
            "User-Agent": "max-freshservice-tickets-import/1",
        }

    def _domain_api_url(self) -> str:
        domain = _optional(self.domain)
        if not domain:
            return ""
        if domain.startswith(("http://", "https://")):
            return domain
        return FRESHSERVICE_API_TEMPLATE.format(domain=domain)


FreshserviceTicketAdapter = FreshserviceTicketsAdapter


def _ticket_signal(ticket: dict[str, Any], *, adapter_name: str, api_url: str) -> Signal:
    ticket_id = _text(ticket.get("id"))
    display_id = _text(ticket.get("display_id"))
    status = _text(ticket.get("status"))
    priority = _text(ticket.get("priority"))
    category = _text(ticket.get("category"))
    created_at = _parse_dt(ticket.get("created_at"))
    requester_id = _text(ticket.get("requester_id"))
    url_id = display_id or ticket_id
    custom_fields = (
        ticket.get("custom_fields") if isinstance(ticket.get("custom_fields"), dict) else {}
    )
    return Signal(
        id=f"freshservice-ticket:{ticket_id}" if ticket_id else "",
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(ticket.get("subject")) or ticket_id,
        content=_text(ticket.get("description_text") or ticket.get("description"))[:1000],
        url=f"{api_url}/a/tickets/{url_id}" if url_id else api_url,
        author=requester_id or None,
        published_at=created_at,
        tags=sorted({"freshservice", status, priority, category} - {""})[:10],
        credibility=0.6,
        metadata={
            "freshservice_ticket_id": ticket.get("id"),
            "ticket_id": ticket.get("id"),
            "display_id": ticket.get("display_id"),
            "requester_id": ticket.get("requester_id"),
            "responder_id": ticket.get("responder_id"),
            "department_id": ticket.get("department_id"),
            "category": ticket.get("category"),
            "sub_category": ticket.get("sub_category"),
            "item_category": ticket.get("item_category"),
            "priority": ticket.get("priority"),
            "status": ticket.get("status"),
            "source": ticket.get("source"),
            "created_at": ticket.get("created_at"),
            "updated_at": ticket.get("updated_at"),
            "due_by": ticket.get("due_by"),
            "custom_fields": custom_fields,
        },
    )


def _basic_token(api_key: str) -> str:
    return base64.b64encode(f"{api_key}:X".encode("utf-8")).decode("ascii")


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
