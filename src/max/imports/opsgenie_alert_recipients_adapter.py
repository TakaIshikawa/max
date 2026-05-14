"""Opsgenie alert recipients import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_OPSGENIE_API_URL = "https://api.opsgenie.com"


class OpsgenieAlertRecipientsImportAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        identifier_type: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("OPSGENIE_API_KEY"))
        self.api_url = _api_root(api_url or _optional(self._config.get("api_url")) or DEFAULT_OPSGENIE_API_URL)
        self._identifier_type = identifier_type
        self._client = client

    @property
    def name(self) -> str:
        return "opsgenie_alert_recipients_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def identifiers(self) -> list[str]:
        return _strings(
            self._config.get("alert_ids")
            or self._config.get("alert_id")
            or self._config.get("aliases")
            or self._config.get("alias")
            or self._config.get("identifiers")
            or self._config.get("identifier")
        )

    @property
    def identifier_type(self) -> str:
        return _optional(self._identifier_type) or _optional(self._config.get("identifier_type")) or _optional(self._config.get("identifierType")) or "id"

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("per_page") or self._config.get("limit") or self._config.get("page_size"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.api_key and self.identifiers):
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            rows: list[tuple[str, dict[str, Any], int]] = []
            for identifier in self.identifiers:
                if len(rows) >= limit:
                    break
                recipients = await self._fetch_recipients(client, identifier=identifier, limit=limit - len(rows))
                if recipients is None:
                    return []
                rows.extend((identifier, recipient, offset) for recipient, offset in recipients)
            return [_recipient_signal(identifier, recipient, offset, self.identifier_type, self.name) for identifier, recipient, offset in rows[:limit]]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_recipients(self, client: httpx.AsyncClient, *, identifier: str, limit: int) -> list[tuple[dict[str, Any], int]] | None:
        recipients: list[tuple[dict[str, Any], int]] = []
        offset = 0
        while len(recipients) < limit:
            page_limit = min(self.page_size, limit - len(recipients))
            body = await self._get(client, f"/v2/alerts/{identifier}/recipients", params={"identifierType": self.identifier_type, "limit": page_limit, "offset": offset})
            if body is None:
                return None
            page = _recipients_from_body(body)
            if not page:
                break
            recipients.extend((recipient, offset + index) for index, recipient in enumerate(page) if isinstance(recipient, dict))
            if len(page) < page_limit or not _has_more(body, page_limit=page_limit):
                break
            offset = _next_offset(body, offset, page_limit)
        return recipients[:limit]

    async def _get(self, client: httpx.AsyncClient, path: str, *, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = await client.get(f"{self.api_url}{path}", params=params, headers=self._headers())
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Opsgenie alert recipients fetch failed", exc_info=True)
            return None
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"GenieKey {self.api_key}",
            "User-Agent": "max-opsgenie-alert-recipients-import/1",
        }


OpsgenieAlertRecipientsAdapter = OpsgenieAlertRecipientsImportAdapter


def _recipient_signal(identifier: str, recipient: dict[str, Any], offset: int, identifier_type: str, adapter_name: str) -> Signal:
    recipient_id = _text(recipient.get("id") or recipient.get("name") or recipient.get("username") or recipient.get("email") or offset)
    recipient_type = _text(recipient.get("type") or recipient.get("recipientType") or recipient.get("entity_type"))
    name = _text(recipient.get("name") or recipient.get("username") or recipient.get("email") or recipient.get("displayName"))
    return Signal(
        id=f"opsgenie-alert-recipient:{identifier}:{recipient_id}",
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Opsgenie alert {identifier} recipient",
        content=name or recipient_type or "Opsgenie alert recipient",
        url=_text(recipient.get("url") or recipient.get("html_url")),
        author=name or None,
        published_at=_parse_dt(recipient.get("createdAt") or recipient.get("created_at")),
        tags=sorted({"opsgenie", "alert", "recipient", recipient_type.lower()} - {""})[:10],
        credibility=0.7,
        metadata={
            "recipient_id": recipient.get("id"),
            "alert_identifier": identifier,
            "identifier_type": identifier_type,
            "recipient_type": recipient_type or None,
            "name": recipient.get("name"),
            "username": recipient.get("username"),
            "email": recipient.get("email"),
            "team": recipient.get("team"),
            "user": recipient.get("user"),
            "escalation": recipient.get("escalation"),
            "status": recipient.get("status"),
            "delivery": recipient.get("delivery") or recipient.get("deliveryStatus"),
            "offset": offset,
            "raw": recipient,
        },
    )


def _recipients_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("recipients"), list):
        return [item for item in data["recipients"] if isinstance(item, dict)]
    if isinstance(body.get("recipients"), list):
        return [item for item in body["recipients"] if isinstance(item, dict)]
    return []


def _has_more(body: dict[str, Any], *, page_limit: int) -> bool:
    if isinstance(body.get("more"), bool):
        return bool(body["more"])
    paging = body.get("paging")
    if isinstance(paging, dict):
        return bool(paging.get("next"))
    data = body.get("data")
    if isinstance(data, dict) and isinstance(data.get("paging"), dict):
        return bool(data["paging"].get("next"))
    return len(_recipients_from_body(body)) >= page_limit


def _next_offset(body: dict[str, Any], offset: int, page_limit: int) -> int:
    for source in (body, body.get("data") if isinstance(body.get("data"), dict) else {}):
        if isinstance(source, dict) and isinstance(source.get("offset"), int):
            return int(source["offset"]) + int(source.get("limit") or page_limit)
    return offset + page_limit


def _api_root(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    for suffix in ("/v2/alerts", "/v2"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


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
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
