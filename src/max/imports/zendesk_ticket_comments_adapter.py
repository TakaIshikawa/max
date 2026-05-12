"""Zendesk ticket comments import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)


class ZendeskTicketCommentsImportAdapter(SourceAdapter):
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
        configured_base = base_url or _optional(self._config.get("base_url")) or os.getenv("ZENDESK_BASE_URL")
        subdomain = _optional(self._config.get("subdomain")) or os.getenv("ZENDESK_SUBDOMAIN")
        self.base_url = (configured_base or (f"https://{subdomain}.zendesk.com" if subdomain else "")).rstrip("/")
        self.email = email if email is not None else (_optional(self._config.get("email")) or os.getenv("ZENDESK_EMAIL"))
        self.token = token if token is not None else (_optional(self._config.get("token")) or _optional(self._config.get("api_token")) or os.getenv("ZENDESK_API_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "zendesk_ticket_comments_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def ticket_ids(self) -> list[str]:
        return _strings(self._config.get("ticket_ids") or self._config.get("ticket_id"))

    @property
    def include_public_only(self) -> bool:
        return bool(self._config.get("include_public_only"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.base_url and self.email and self.token and self.ticket_ids):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen: set[str] = set()
            for ticket_id in self.ticket_ids:
                if len(signals) >= limit:
                    break
                comments = await self._fetch_ticket_comments(
                    client,
                    ticket_id=ticket_id,
                    limit=limit - len(signals),
                )
                for comment in comments:
                    if self.include_public_only and comment.get("public") is not True:
                        continue
                    signal = _comment_signal(comment, ticket_id, self.name, self.base_url, seen)
                    if signal:
                        signals.append(signal)
                    if len(signals) >= limit:
                        break
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_ticket_comments(
        self,
        client: httpx.AsyncClient,
        *,
        ticket_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        comments: list[dict[str, Any]] = []
        url = f"{self.base_url}/api/v2/tickets/{ticket_id}/comments.json"
        params: dict[str, Any] | None = None
        while url and len(comments) < limit:
            body = await self._get(client, url=url, params=params)
            page = body.get("comments") if isinstance(body.get("comments"), list) else []
            comments.extend(item for item in page if isinstance(item, dict))
            url = _optional(body.get("next_page")) or _optional(((body.get("links") or {}) if isinstance(body.get("links"), dict) else {}).get("next"))
            params = None
            if not page:
                break
        return comments[:limit]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(url, auth=(f"{self.email}/token", self.token or ""), params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Zendesk ticket comment fetch failed for %s", url, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


ZendeskTicketCommentsAdapter = ZendeskTicketCommentsImportAdapter


def _comment_signal(
    comment: dict[str, Any],
    ticket_id: str,
    adapter_name: str,
    base_url: str,
    seen: set[str],
) -> Signal | None:
    comment_id = _optional(comment.get("id"))
    if not comment_id:
        return None
    external_id = f"zendesk-ticket-comment:{ticket_id}:{comment_id}"
    if external_id in seen:
        return None
    seen.add(external_id)

    public = comment.get("public")
    visibility = "public" if public is True else "private" if public is False else ""
    attachments = comment.get("attachments") if isinstance(comment.get("attachments"), list) else []
    body = _text(comment.get("body")) or _html_body_text(comment.get("html_body"))

    return Signal(
        id=external_id,
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=f"Zendesk ticket {ticket_id} comment",
        content=body[:1000],
        url=f"{base_url}/agent/tickets/{ticket_id}",
        author=_text(comment.get("author_id")) or None,
        published_at=_parse_dt(comment.get("created_at")),
        tags=sorted({"zendesk", "ticket-comment", visibility} - {""})[:10],
        credibility=0.6,
        metadata={
            "ticket_id": ticket_id,
            "comment_id": comment.get("id"),
            "author_id": comment.get("author_id"),
            "public": public,
            "visibility": visibility,
            "attachments_count": len(attachments),
            "audit_id": comment.get("audit_id"),
            "body": body,
            "html_body": _text(comment.get("html_body")) or None,
            "plain_body": _text(comment.get("plain_body")) or None,
            "created_at": comment.get("created_at"),
            "raw": comment,
        },
    )


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
