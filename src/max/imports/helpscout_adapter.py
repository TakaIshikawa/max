"""Help Scout conversation import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
HELPSCOUT_API = "https://api.helpscout.net/v2"


class HelpScoutAdapter(SourceAdapter):
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
            else (_optional(self._config.get("token")) or os.getenv("HELPSCOUT_API_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or HELPSCOUT_API).rstrip(
            "/"
        )
        self._client = client

    @property
    def name(self) -> str:
        return "helpscout_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def mailbox(self) -> str | None:
        return _optional(self._config.get("mailbox") or self._config.get("mailbox_id"))

    @property
    def status(self) -> str | None:
        return _optional(self._config.get("status"))

    @property
    def page_size(self) -> int:
        value = self._config.get("page_size")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return min(value, 100)
        return 50

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            conversations: list[dict[str, Any]] = []
            page = 1
            while len(conversations) < limit:
                body = await self._get_page(client, page=page)
                page_items = _embedded_list(body, "conversations")
                if not page_items:
                    break
                conversations.extend(page_items)
                pages = _page_count(body)
                if page >= pages or len(page_items) < self.page_size:
                    break
                page += 1
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for conversation in conversations:
            if not isinstance(conversation, dict):
                continue
            conversation_id = _text(conversation.get("id"))
            if not conversation_id or conversation_id in seen:
                continue
            seen.add(conversation_id)
            signals.append(_conversation_signal(conversation, self.name, self.api_url))
            if len(signals) >= limit:
                break
        return signals

    async def _get_page(self, client: httpx.AsyncClient, *, page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "pageSize": self.page_size}
        if self.mailbox:
            params["mailbox"] = self.mailbox
        if self.status:
            params["status"] = self.status
        try:
            response = await client.get(
                f"{self.api_url}/conversations",
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Help Scout conversation fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


HelpScoutConversationAdapter = HelpScoutAdapter


def _conversation_signal(conversation: dict[str, Any], adapter_name: str, api_url: str) -> Signal:
    conversation_id = _text(conversation.get("id"))
    mailbox = _object_summary(conversation.get("mailbox"))
    customer = _person(conversation.get("primaryCustomer") or conversation.get("customer"))
    assignee = _person(conversation.get("assignee"))
    tags = _tag_names(conversation.get("tags"))
    status = _text(conversation.get("status"))
    conv_type = _text(conversation.get("type"))
    body = _text(
        conversation.get("preview") or conversation.get("body") or conversation.get("text")
    )
    url = _text(conversation.get("webUrl") or conversation.get("url")) or (
        f"{api_url}/conversations/{conversation_id}" if conversation_id else api_url
    )
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(conversation.get("subject")) or conversation_id,
        content=body[:1000],
        url=url,
        author=customer.get("email") or customer.get("name") or None,
        published_at=_parse_dt(conversation.get("createdAt")),
        tags=sorted({"helpscout", status, conv_type, _text(mailbox.get("name")), *tags} - {""})[
            :10
        ],
        credibility=0.6,
        metadata={
            "helpscout_conversation_id": conversation.get("id"),
            "number": conversation.get("number"),
            "status": conversation.get("status"),
            "type": conversation.get("type"),
            "mailbox": mailbox,
            "customer": customer,
            "assignee": assignee,
            "tags": tags,
            "created_at": conversation.get("createdAt"),
            "modified_at": conversation.get("modifiedAt"),
            "closed_at": conversation.get("closedAt"),
        },
    )


def _embedded_list(body: dict[str, Any], key: str) -> list[dict[str, Any]]:
    embedded = body.get("_embedded") if isinstance(body.get("_embedded"), dict) else {}
    value = embedded.get(key) if isinstance(embedded, dict) else None
    if not isinstance(value, list):
        value = body.get(key)
    return value if isinstance(value, list) else []


def _page_count(body: dict[str, Any]) -> int:
    page = body.get("page") if isinstance(body.get("page"), dict) else {}
    return max(_int(page.get("totalPages"), 1), 1)


def _object_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {"id": value.get("id"), "name": value.get("name")}


def _person(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    name = _text(value.get("name")) or " ".join(
        part for part in [_text(value.get("first")), _text(value.get("last"))] if part
    )
    return {"id": value.get("id"), "name": name or None, "email": value.get("email")}


def _tag_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = _text(item.get("tag") or item.get("name")) if isinstance(item, dict) else _text(item)
        if name:
            names.append(name)
    return names


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
