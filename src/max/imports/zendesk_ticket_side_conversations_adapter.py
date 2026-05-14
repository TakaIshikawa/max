"""Zendesk ticket side conversations import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketSideConversationsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        api_url: str | None = None,
        base_url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        api_token: str | None = None,
        oauth_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        configured_base = api_url or base_url or _optional(self._config.get("api_url")) or _optional(self._config.get("base_url")) or os.getenv("ZENDESK_BASE_URL")
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.api_token = api_token if api_token is not None else (
            token or _optional(self._config.get("api_token")) or _optional(self._config.get("token")) or os.getenv("ZENDESK_API_TOKEN")
        )
        self.oauth_token = oauth_token if oauth_token is not None else (_optional(self._config.get("oauth_token")) or os.getenv("ZENDESK_OAUTH_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_ticket_side_conversations_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def ticket_ids(self) -> list[str]:
        return _strings(self._config.get("ticket_ids") or self._config.get("ticket_id"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("page_size"), default=100, maximum=100)

    @property
    def _has_auth(self) -> bool:
        return bool(self.oauth_token or (self.email and self.api_token))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.ticket_ids and self._has_auth):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any]]] = []
            for ticket_id in self.ticket_ids:
                if len(rows) >= limit:
                    break
                conversations = await self._fetch_ticket_conversations(client, ticket_id=ticket_id, limit=limit - len(rows))
                if conversations is None:
                    return []
                rows.extend((ticket_id, conversation) for conversation in conversations)
            return [_conversation_signal(ticket_id, conversation, self.name, self.base_url) for ticket_id, conversation in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_ticket_conversations(self, client: httpx.AsyncClient, *, ticket_id: str, limit: int) -> list[dict[str, Any]] | None:
        conversations: list[dict[str, Any]] = []
        url = f"{self.base_url}/api/v2/tickets/{ticket_id}/side_conversations.json"
        params: dict[str, Any] | None = {"page[size]": min(self.page_size, limit), "per_page": min(self.page_size, limit)}
        while url and len(conversations) < limit:
            body = await self._get(client, url=url, params=params)
            if body is None:
                return None
            page = body.get("side_conversations") if isinstance(body.get("side_conversations"), list) else []
            if not page:
                break
            conversations.extend(item for item in page if isinstance(item, dict))
            links = body.get("links") if isinstance(body.get("links"), dict) else {}
            url = _optional(body.get("next_page")) or _optional(links.get("next"))
            params = None
        return conversations[:limit]

    async def _get(self, client: httpx.AsyncClient, *, url: str, params: dict[str, Any] | None) -> dict[str, Any] | None:
        headers = {"Accept": "application/json", "User-Agent": "max-zendesk-ticket-side-conversations-import/1"}
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
            logger.warning("Zendesk ticket side conversations fetch failed for %s", url, exc_info=True)
            return None
        return body if isinstance(body, dict) else {}


ZendeskTicketSideConversationsAdapter = ZendeskTicketSideConversationsImportAdapter


def _conversation_signal(ticket_id: str, conversation: dict[str, Any], adapter_name: str, base_url: str) -> Signal:
    conversation_id = _text(conversation.get("id") or conversation.get("side_conversation_id") or conversation.get("created_at"))
    subject = _text(conversation.get("subject")) or f"Zendesk ticket {ticket_id} side conversation"
    state = _text(conversation.get("state") or conversation.get("status"))
    return Signal(
        id=f"zendesk-ticket-side-conversation:{ticket_id}:{conversation_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=subject,
        content=_content(conversation, subject)[:1000],
        url=_text(conversation.get("url") or conversation.get("html_url")) or f"{base_url}/agent/tickets/{ticket_id}",
        author=_author(conversation),
        published_at=_parse_dt(conversation.get("created_at")),
        tags=sorted({"zendesk", "ticket", "side-conversation", state.lower()} - {""})[:10],
        credibility=0.65,
        metadata={
            "side_conversation_id": conversation.get("id") or conversation.get("side_conversation_id"),
            "ticket_id": ticket_id,
            "subject": conversation.get("subject"),
            "state": conversation.get("state") or conversation.get("status"),
            "participants": conversation.get("participants"),
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "url": conversation.get("url") or conversation.get("html_url"),
            "raw": conversation,
        },
    )


def _content(conversation: dict[str, Any], subject: str) -> str:
    for key in ("preview_text", "message", "body", "html_body", "text"):
        value = _optional(conversation.get(key))
        if value:
            return value
    messages = conversation.get("messages") if isinstance(conversation.get("messages"), list) else []
    for message in messages:
        if isinstance(message, dict):
            value = _optional(message.get("body") or message.get("text") or message.get("preview_text"))
            if value:
                return value
    return subject


def _author(conversation: dict[str, Any]) -> str | None:
    for key in ("created_by", "author", "actor"):
        value = conversation.get(key)
        if isinstance(value, dict):
            return _optional(value.get("email") or value.get("name") or value.get("id"))
    return None


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
