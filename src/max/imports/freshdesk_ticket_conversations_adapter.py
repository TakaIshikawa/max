"""Freshdesk ticket conversations import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class FreshdeskTicketConversationsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        domain: str | None = None,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_domain = domain or _optional(self._config.get("domain")) or os.getenv("FRESHDESK_DOMAIN")
        self.domain = _freshdesk_domain(configured_domain)
        self.api_key = (
            api_key
            if api_key is not None
            else (_optional(self._config.get("api_key")) or os.getenv("FRESHDESK_API_KEY"))
        )
        self._client = client

    @property
    def name(self) -> str:
        return "freshdesk_ticket_conversations_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}" if self.domain else ""

    @property
    def ticket_ids(self) -> list[str]:
        return _strings(self._config.get("ticket_ids") or self._config.get("ticket_id"))

    @property
    def include_private_notes(self) -> bool:
        return bool(self._config.get("include_private_notes"))

    @property
    def updated_since(self) -> str | None:
        return _optional(self._config.get("updated_since"))

    @property
    def per_ticket_limit(self) -> int:
        return _positive_int(self._config.get("per_ticket_limit"), default=30, maximum=1000)

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page"),
            default=min(self.per_ticket_limit, 30),
            maximum=100,
        )

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.domain and self.api_key and self.ticket_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for ticket_id in self.ticket_ids:
                if len(signals) >= limit:
                    break
                conversations = await self._fetch_ticket_conversations(
                    client,
                    ticket_id=ticket_id,
                    limit=min(self.per_ticket_limit, limit - len(signals)),
                )
                for conversation in conversations:
                    if conversation.get("private") is True and not self.include_private_notes:
                        continue
                    if self.updated_since and not _updated_on_or_after(conversation, self.updated_since):
                        continue
                    signal = _conversation_signal(conversation, ticket_id, self.name, self.base_url, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_ticket_conversations(
        self,
        client: httpx.AsyncClient,
        *,
        ticket_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        conversations: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/tickets/{ticket_id}/conversations"
        params: dict[str, Any] | None = {
            "page": 1,
            "per_page": min(self.page_size, limit),
        }
        if self.updated_since:
            params["updated_since"] = self.updated_since

        while url and len(conversations) < limit:
            response = await self._get(client, url=url, params=params)
            if response is None:
                break
            body = response.json()
            page = body if isinstance(body, list) else body.get("conversations", [])
            values = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
            conversations.extend(values)

            next_url = _response_next_url(response)
            if next_url:
                url = next_url
                params = None
            elif values and params and len(values) >= int(params["per_page"]):
                params = {**params, "page": int(params["page"]) + 1}
            else:
                break
        return conversations[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> httpx.Response | None:
        try:
            response = await client.get(
                url,
                auth=httpx.BasicAuth(self.api_key or "", "X"),
                headers={"Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
        except Exception:
            logger.warning("Freshdesk ticket conversation fetch failed for %s", url, exc_info=True)
            return None
        return response


FreshdeskTicketConversationsAdapter = FreshdeskTicketConversationsImportAdapter


def _conversation_signal(
    conversation: dict[str, Any],
    ticket_id: str,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    conversation_id = _optional(conversation.get("id"))
    if not conversation_id:
        return None
    external_id = f"freshdesk-ticket-conversation:{ticket_id}:{conversation_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    private = conversation.get("private")
    visibility = "private" if private is True else "public" if private is False else ""
    kind = _conversation_kind(conversation)
    attachments = conversation.get("attachments") if isinstance(conversation.get("attachments"), list) else []
    body = _text(conversation.get("body_text")) or _html_body_text(conversation.get("body"))

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Freshdesk ticket {ticket_id} {kind}",
        content=body[:1000],
        url=f"{base_url}/a/tickets/{ticket_id}",
        author=_text(conversation.get("user_id")) or _text(conversation.get("from_email")) or None,
        published_at=_parse_dt(conversation.get("created_at")),
        tags=sorted({"freshdesk", "ticket-conversation", kind, visibility} - {""})[:10],
        credibility=0.6,
        metadata={
            "ticket_id": ticket_id,
            "conversation_id": conversation.get("id"),
            "user_id": conversation.get("user_id"),
            "from_email": _text(conversation.get("from_email")) or None,
            "incoming": conversation.get("incoming"),
            "private": private,
            "visibility": visibility,
            "kind": kind,
            "source": conversation.get("source"),
            "attachments_count": len(attachments),
            "body": body,
            "body_text": _text(conversation.get("body_text")) or None,
            "html_body": _text(conversation.get("body")) or None,
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "raw": conversation,
        },
    )


def _conversation_kind(conversation: dict[str, Any]) -> str:
    if conversation.get("private") is True:
        return "note"
    if conversation.get("incoming") is True:
        return "reply"
    return "conversation"


def _response_next_url(response: httpx.Response) -> str | None:
    next_link = response.links.get("next")
    if isinstance(next_link, dict):
        return _optional(next_link.get("url"))
    links_header = response.headers.get("Link", "")
    for part in links_header.split(","):
        if 'rel="next"' not in part and "rel=next" not in part:
            continue
        start = part.find("<")
        end = part.find(">", start + 1)
        if start >= 0 and end > start:
            return _optional(part[start + 1 : end])
    return None


def _updated_on_or_after(conversation: dict[str, Any], updated_since: str) -> bool:
    threshold = _parse_dt(updated_since)
    if threshold is None:
        return True
    value = _parse_dt(conversation.get("updated_at")) or _parse_dt(conversation.get("created_at"))
    return value is not None and value >= threshold


def _freshdesk_domain(value: object) -> str:
    domain = _text(value).removeprefix("https://").removeprefix("http://").strip("/")
    if not domain:
        return ""
    if "." not in domain:
        return f"{domain}.freshdesk.com"
    return domain


def _html_body_text(value: object) -> str:
    html = _text(value)
    if not html:
        return ""
    return html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")


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
