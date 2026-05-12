"""Opsgenie alert notes import adapter."""

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


class OpsgenieAlertNotesImportAdapter(SourceAdapter):
    """Fetch notes for a specific Opsgenie alert and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        alert_id: str | None = None,
        identifier: str | None = None,
        identifier_type: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = (
            api_key
            if api_key is not None
            else (_optional(self._config.get("api_key")) or os.getenv("OPSGENIE_API_KEY"))
        )
        self.api_url = _api_root(
            api_url or _optional(self._config.get("api_url")) or DEFAULT_OPSGENIE_API_URL
        )
        self._alert_id = alert_id
        self._identifier = identifier
        self._identifier_type = identifier_type
        self._client = client

    @property
    def name(self) -> str:
        return "opsgenie_alert_notes_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def identifier(self) -> str | None:
        return (
            _optional(self._identifier)
            or _optional(self._alert_id)
            or _optional(self._config.get("identifier"))
            or _optional(self._config.get("alert_id"))
        )

    @property
    def identifier_type(self) -> str:
        return (
            _optional(self._identifier_type)
            or _optional(self._config.get("identifier_type"))
            or _optional(self._config.get("identifierType"))
            or "id"
        )

    @property
    def order(self) -> str | None:
        return _optional(self._config.get("order"))

    @property
    def page_size(self) -> int:
        configured = self._config.get("page_size")
        if configured is None:
            configured = self._config.get("limit")
        return _positive_int(configured, default=100, maximum=100)

    @property
    def initial_offset(self) -> int:
        return _non_negative_int(self._config.get("offset"), default=0)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        identifier = self.identifier
        if limit <= 0 or not self.api_key or not identifier:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            notes = await self._fetch_notes(client, identifier=identifier, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for note, offset in notes:
            signal = _note_signal(
                note,
                alert_identifier=identifier,
                identifier_type=self.identifier_type,
                offset=offset,
                adapter_name=self.name,
                seen=seen,
            )
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_notes(
        self,
        client: httpx.AsyncClient,
        *,
        identifier: str,
        limit: int,
    ) -> list[tuple[dict[str, Any], int]]:
        notes: list[tuple[dict[str, Any], int]] = []
        offset = self.initial_offset
        while len(notes) < limit:
            page_limit = min(self.page_size, limit - len(notes))
            body = await self._get(
                client,
                f"/v2/alerts/{identifier}/notes",
                params=self._params(limit=page_limit, offset=offset),
            )
            page = _notes_from_body(body)
            if not page:
                break
            notes.extend((note, offset + index) for index, note in enumerate(page) if isinstance(note, dict))
            if len(page) < page_limit or not _has_more(body, page_limit=page_limit):
                break
            offset = _next_offset(body, offset, page_limit)
        return notes[:limit]

    def _params(self, *, limit: int, offset: int) -> dict[str, Any]:
        params: dict[str, Any] = {
            "identifierType": self.identifier_type,
            "limit": limit,
            "offset": offset,
        }
        if self.order:
            params["order"] = self.order
        return params

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.api_url}{path}",
                params=params,
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Opsgenie alert notes fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"GenieKey {self.api_key}",
            "User-Agent": "max-opsgenie-alert-notes-import/1",
        }


OpsgenieAlertNotesAdapter = OpsgenieAlertNotesImportAdapter


def _note_signal(
    note: dict[str, Any],
    *,
    alert_identifier: str,
    identifier_type: str,
    offset: int,
    adapter_name: str,
    seen: set[str],
) -> Signal | None:
    note_id = _optional(note.get("id") or note.get("noteId"))
    if not note_id:
        return None
    signal_id = f"opsgenie-alert-note:{alert_identifier}:{note_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    note_text = _text(note.get("note") or note.get("text") or note.get("content"))
    owner = _owner(note.get("owner"))
    created_at = _optional(note.get("createdAt") or note.get("created_at"))
    source = _optional(note.get("source")) or "opsgenie"
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"Opsgenie alert {alert_identifier} note",
        content=note_text[:1000],
        url=_text(note.get("url") or note.get("html_url")),
        author=owner,
        published_at=_parse_dt(created_at),
        tags=["opsgenie", "alert", "note"],
        credibility=0.7,
        metadata={
            "opsgenie_note_id": note_id,
            "alert_identifier": alert_identifier,
            "identifier_type": identifier_type,
            "note": note_text,
            "owner": _owner_metadata(note.get("owner")),
            "createdAt": created_at,
            "source": source,
            "offset": offset,
            "source_adapter": adapter_name,
            "raw": note,
        },
    )


def _notes_from_body(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("notes"), list):
        return [item for item in data["notes"] if isinstance(item, dict)]
    if isinstance(body.get("notes"), list):
        return [item for item in body["notes"] if isinstance(item, dict)]
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
    return len(_notes_from_body(body)) >= page_limit


def _next_offset(body: dict[str, Any], offset: int, page_limit: int) -> int:
    for source in (body, body.get("data") if isinstance(body.get("data"), dict) else {}):
        if isinstance(source, dict) and isinstance(source.get("offset"), int):
            return int(source["offset"]) + int(source.get("limit") or page_limit)
    return offset + page_limit


def _owner(value: object) -> str | None:
    if isinstance(value, dict):
        return (
            _optional(value.get("username"))
            or _optional(value.get("name"))
            or _optional(value.get("email"))
            or _optional(value.get("id"))
        )
    return _optional(value)


def _owner_metadata(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "id": value.get("id"),
            "name": value.get("name"),
            "username": value.get("username"),
            "email": value.get("email"),
        }
    return {"name": _optional(value)}


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _api_root(value: str) -> str:
    url = value.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    for suffix in ("/v2/alerts", "/v2"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number <= 0:
        return default
    return min(number, maximum)


def _non_negative_int(value: object, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
