"""HubSpot tickets import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
HUBSPOT_API = "https://api.hubapi.com"
DEFAULT_TICKET_PROPERTIES = [
    "subject",
    "content",
    "hs_pipeline",
    "hs_pipeline_stage",
    "hs_ticket_priority",
    "hs_ticket_category",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotTicketsAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.token = (
            token
            if token is not None
            else (_optional(self._config.get("token")) or os.getenv("HUBSPOT_ACCESS_TOKEN"))
        )
        self.api_url = (
            api_url or _optional(self._config.get("api_url")) or os.getenv("HUBSPOT_API_URL") or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_tickets_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        configured = _strings(self._config.get("properties"))
        return configured or DEFAULT_TICKET_PROPERTIES

    @property
    def archived(self) -> bool | None:
        value = self._config.get("archived")
        if isinstance(value, bool):
            return value
        text = _text(value).lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return None

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_limit(self) -> int:
        return _positive_int(self._config.get("limit"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            tickets = await self._fetch_tickets(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [
            _ticket_signal(ticket, self.name)
            for ticket in tickets[:limit]
            if isinstance(ticket, dict)
        ]

    async def _fetch_tickets(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        tickets: list[dict[str, Any]] = []
        after = self.after
        while len(tickets) < limit:
            page_size = min(self.page_limit, limit - len(tickets))
            body = await self._get(client, limit=page_size, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            tickets.extend(item for item in results if isinstance(item, dict))
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return tickets[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "properties": self.properties}
        if after:
            params["after"] = after
        if self.archived is not None:
            params["archived"] = str(self.archived).lower()
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/tickets",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-tickets-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot tickets fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


HubSpotTicketAdapter = HubSpotTicketsAdapter


def _ticket_signal(ticket: dict[str, Any], adapter_name: str) -> Signal:
    props = ticket.get("properties") if isinstance(ticket.get("properties"), dict) else {}
    ticket_id = _text(ticket.get("id"))
    subject = _text(props.get("subject")) or f"HubSpot ticket {ticket_id}"
    content = _text(props.get("content"))
    pipeline = _text(props.get("hs_pipeline"))
    stage = _text(props.get("hs_pipeline_stage"))
    priority = _text(props.get("hs_ticket_priority"))
    category = _text(props.get("hs_ticket_category"))
    return Signal(
        id=f"hubspot-ticket:{ticket_id}" if ticket_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=subject,
        content=content or f"HubSpot ticket stage: {stage or 'unknown'}",
        url=_ticket_url(ticket),
        author=_text(props.get("hubspot_owner_id")) or None,
        published_at=_parse_dt(props.get("createdate") or ticket.get("createdAt")),
        tags=sorted({"hubspot", "ticket", pipeline, stage, priority, category} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_ticket_id": ticket.get("id"),
            "ticket_id": ticket.get("id"),
            "subject": subject,
            "content": content or None,
            "pipeline": pipeline or None,
            "stage": stage or None,
            "priority": priority or None,
            "category": category or None,
            "created_at": props.get("createdate") or ticket.get("createdAt"),
            "updated_at": props.get("hs_lastmodifieddate") or ticket.get("updatedAt"),
            "archived": ticket.get("archived"),
            "properties": props,
            "raw": ticket,
        },
    )


def _ticket_url(ticket: dict[str, Any]) -> str:
    if _text(ticket.get("url")):
        return _text(ticket.get("url"))
    ticket_id = _text(ticket.get("id"))
    return f"https://app.hubspot.com/contacts/ticket/{ticket_id}" if ticket_id else ""


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


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


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
