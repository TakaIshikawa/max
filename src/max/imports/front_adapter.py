"""Front conversation import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
FRONT_API = "https://api2.frontapp.com"


class FrontAdapter(SourceAdapter):
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
            else (_optional(self._config.get("token")) or os.getenv("FRONT_API_TOKEN"))
        )
        self.api_url = (api_url or _optional(self._config.get("api_url")) or FRONT_API).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "front_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def inbox_id(self) -> str | None:
        return _optional(self._config.get("inbox_id") or self._config.get("inbox"))

    @property
    def channel_id(self) -> str | None:
        return _optional(self._config.get("channel_id") or self._config.get("channel"))

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
            url = self._initial_url()
            params: dict[str, Any] | None = self._initial_params()
            while url and len(conversations) < limit:
                body = await self._get(client, url=url, params=params)
                page = body.get("_results") if isinstance(body.get("_results"), list) else []
                if not page:
                    break
                conversations.extend(page)
                url = _next_link(body)
                params = None
                if len(page) < self.page_size:
                    break
        finally:
            if close_client:
                await client.aclose()
        return [
            _conversation_signal(item, self.name)
            for item in conversations[:limit]
            if isinstance(item, dict)
        ]

    def _initial_url(self) -> str:
        if self.inbox_id:
            return f"{self.api_url}/inboxes/{self.inbox_id}/conversations"
        return f"{self.api_url}/conversations"

    def _initial_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": self.page_size}
        if self.channel_id:
            params["channel_id"] = self.channel_id
        if self.status:
            params["q[statuses]"] = self.status
        return params

    async def _get(
        self, client: httpx.AsyncClient, *, url: str, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Front conversation fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


FrontConversationAdapter = FrontAdapter


def _conversation_signal(conversation: dict[str, Any], adapter_name: str) -> Signal:
    metadata = (
        conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
    )
    assignee = (
        conversation.get("assignee") if isinstance(conversation.get("assignee"), dict) else {}
    )
    recipient = _first_recipient(conversation)
    tags = _tag_names(conversation.get("tags"))
    inboxes = [_summary(item) for item in conversation.get("inboxes", []) if isinstance(item, dict)]
    links = conversation.get("_links") if isinstance(conversation.get("_links"), dict) else {}
    url = _text(links.get("self") or conversation.get("link") or conversation.get("url"))
    content = _text(
        conversation.get("latest_message") or conversation.get("body") or metadata.get("excerpt")
    )
    status = _text(conversation.get("status"))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(conversation.get("subject")) or _text(conversation.get("id")),
        content=content[:1000],
        url=url,
        author=recipient.get("handle") or recipient.get("name") or None,
        published_at=_parse_timestamp(conversation.get("created_at")),
        tags=sorted({"front", status, *tags} - {""})[:10],
        credibility=0.6,
        metadata={
            "front_conversation_id": conversation.get("id"),
            "status": conversation.get("status"),
            "recipient": recipient,
            "assignee": _summary(assignee),
            "inboxes": inboxes,
            "tags": tags,
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "is_private": conversation.get("is_private"),
        },
    )


def _next_link(body: dict[str, Any]) -> str | None:
    pagination = body.get("_pagination") if isinstance(body.get("_pagination"), dict) else {}
    links = body.get("_links") if isinstance(body.get("_links"), dict) else {}
    return _optional(pagination.get("next") or links.get("next"))


def _first_recipient(conversation: dict[str, Any]) -> dict[str, Any]:
    recipients = conversation.get("recipients")
    if isinstance(recipients, list) and recipients:
        first = recipients[0]
        if isinstance(first, dict):
            return {"name": first.get("name"), "handle": first.get("handle") or first.get("email")}
    return {}


def _summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": value.get("id"),
        "name": value.get("name") or value.get("username"),
        "email": value.get("email"),
    }


def _tag_names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = _text(item.get("name")) if isinstance(item, dict) else _text(item)
        if name:
            names.append(name)
    return names


def _parse_timestamp(value: object) -> datetime | None:
    try:
        if value in (None, ""):
            return None
        if isinstance(value, int | float):
            return datetime.fromtimestamp(float(value))
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OSError):
        return None


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
