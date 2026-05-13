"""Freshdesk ticket attachments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class FreshdeskTicketAttachmentsImportAdapter(SourceAdapter):
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
        return "freshdesk_ticket_attachments_import"

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
    def include_private(self) -> bool:
        return bool(self._config.get("include_private") or self._config.get("include_private_notes"))

    @property
    def updated_since(self) -> str | None:
        return _optional(self._config.get("updated_since"))

    @property
    def per_page(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("page_size"), default=30, maximum=100)

    @property
    def per_ticket_limit(self) -> int:
        return _positive_int(self._config.get("per_ticket_limit"), default=100, maximum=1000)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.domain and self.api_key):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            ticket_ids = self.ticket_ids
            if not ticket_ids:
                ticket_ids = await self._fetch_recent_ticket_ids(client, limit=limit)
            signals: list[Signal] = []
            seen: set[str] = set()
            for ticket_id in ticket_ids:
                if len(signals) >= limit:
                    break
                conversations = await self._fetch_ticket_conversations(
                    client,
                    ticket_id=ticket_id,
                    limit=self.per_ticket_limit,
                )
                for conversation in conversations:
                    if conversation.get("private") is True and not self.include_private:
                        continue
                    if self.updated_since and not _updated_on_or_after(conversation, self.updated_since):
                        continue
                    for attachment in _attachments(conversation):
                        signal = _attachment_signal(
                            attachment,
                            conversation,
                            ticket_id=ticket_id,
                            adapter_name=self.name,
                            base_url=self.base_url,
                            seen=seen,
                        )
                        if signal:
                            signals.append(signal)
                        if len(signals) >= limit:
                            break
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_recent_ticket_ids(self, client: httpx.AsyncClient, *, limit: int) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        url: str | None = f"{self.base_url}/api/v2/tickets"
        params: dict[str, Any] | None = {"page": 1, "per_page": min(self.per_page, limit)}
        if self.updated_since:
            params["updated_since"] = self.updated_since

        while url and len(ids) < limit:
            response = await self._get(client, url=url, params=params)
            if response is None:
                break
            body = response.json()
            page = body.get("tickets", []) if isinstance(body, dict) else body
            values = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
            for ticket in values:
                ticket_id = _optional(ticket.get("id"))
                if ticket_id and ticket_id not in seen:
                    seen.add(ticket_id)
                    ids.append(ticket_id)
                    if len(ids) >= limit:
                        break

            next_url = _response_next_url(response)
            if next_url:
                url = next_url
                params = None
            elif values and params and len(values) >= int(params["per_page"]):
                params = {**params, "page": int(params["page"]) + 1}
            else:
                break
        return ids[:limit]

    async def _fetch_ticket_conversations(
        self,
        client: httpx.AsyncClient,
        *,
        ticket_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        conversations: list[dict[str, Any]] = []
        url: str | None = f"{self.base_url}/api/v2/tickets/{ticket_id}/conversations"
        params: dict[str, Any] | None = {"page": 1, "per_page": min(self.per_page, limit)}
        if self.updated_since:
            params["updated_since"] = self.updated_since

        while url and len(conversations) < limit:
            response = await self._get(client, url=url, params=params)
            if response is None:
                break
            body = response.json()
            page = body.get("conversations", []) if isinstance(body, dict) else body
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
            logger.warning("Freshdesk ticket attachment fetch failed for %s", url, exc_info=True)
            return None
        return response


FreshdeskTicketAttachmentsAdapter = FreshdeskTicketAttachmentsImportAdapter


def _attachment_signal(
    attachment: dict[str, Any],
    conversation: dict[str, Any],
    *,
    ticket_id: str,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    conversation_id = _optional(conversation.get("id"))
    attachment_key = _optional(attachment.get("id") or attachment.get("attachment_id") or attachment.get("url"))
    filename = _text(attachment.get("name") or attachment.get("filename") or attachment.get("file_name"))
    if not conversation_id or not (attachment_key or filename):
        return None

    external_id = f"freshdesk-ticket-attachment:{ticket_id}:{conversation_id}:{attachment_key or filename}"
    if external_id in seen:
        return None
    seen.add(external_id)

    uploader = _optional(conversation.get("user_id") or conversation.get("from_email"))
    download_url = _attachment_url(attachment)
    content_type = _optional(attachment.get("content_type"))
    size = attachment.get("size") or attachment.get("file_size")

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Freshdesk ticket {ticket_id} attachment {filename or attachment_key}",
        content=_text(conversation.get("body_text") or conversation.get("body"))[:1000],
        url=download_url or f"{base_url}/a/tickets/{ticket_id}",
        author=uploader,
        published_at=_parse_dt(conversation.get("created_at")),
        tags=sorted({"freshdesk", "ticket-attachment", content_type or ""} - {""})[:10],
        credibility=0.6,
        metadata={
            "ticket_id": ticket_id,
            "conversation_id": conversation.get("id"),
            "attachment_id": attachment.get("id") or attachment.get("attachment_id"),
            "filename": filename or None,
            "content_type": content_type,
            "size": size,
            "uploader": uploader,
            "user_id": conversation.get("user_id"),
            "from_email": _optional(conversation.get("from_email")),
            "private": conversation.get("private"),
            "incoming": conversation.get("incoming"),
            "attachment_url": download_url or None,
            "ticket_url": f"{base_url}/a/tickets/{ticket_id}",
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at"),
            "raw": {"attachment": attachment, "conversation": conversation},
        },
    )


def _attachments(conversation: dict[str, Any]) -> list[dict[str, Any]]:
    value = conversation.get("attachments")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _attachment_url(attachment: dict[str, Any]) -> str:
    return _text(
        attachment.get("attachment_url")
        or attachment.get("url")
        or attachment.get("download_url")
        or attachment.get("content_url")
    )


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
