"""PagerDuty incident notes import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_PAGERDUTY_API_URL = "https://api.pagerduty.com"


class PagerDutyIncidentNotesAdapter(SourceAdapter):
    """Fetch PagerDuty incident notes and convert them to Max signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_token: str | None = None,
        from_email: str | None = None,
        api_url: str = DEFAULT_PAGERDUTY_API_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_token = api_token if api_token is not None else (
            _optional(self._config.get("api_token")) or os.getenv("PAGERDUTY_API_TOKEN")
        )
        self.from_email = from_email if from_email is not None else (
            _optional(self._config.get("from_email")) or os.getenv("PAGERDUTY_FROM_EMAIL")
        )
        self.api_url = (_optional(self._config.get("api_url")) or api_url).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "pagerduty_incident_notes_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.FAILURE_DATA.value

    @property
    def incident_ids(self) -> list[str]:
        values = self._config.get("incident_ids")
        if values is None:
            values = self._config.get("incident_id")
        if isinstance(values, str):
            return [item.strip() for item in values.split(",") if item.strip()]
        if isinstance(values, list | tuple | set):
            return [str(item).strip() for item in values if str(item).strip()]
        return []

    @property
    def query_params(self) -> dict[str, Any]:
        params = self._config.get("query_params")
        if isinstance(params, dict):
            return {str(key): value for key, value in params.items() if value is not None}
        return {}

    @property
    def web_url(self) -> str | None:
        return _optional(self._config.get("web_url"))

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=100, maximum=100)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            incident_ids = self.incident_ids or await self._fetch_incident_ids(client, limit=limit)
            notes: list[tuple[str, dict[str, Any]]] = []
            for incident_id in incident_ids:
                if len(notes) >= limit:
                    break
                notes.extend(await self._fetch_notes(client, incident_id=incident_id, limit=limit - len(notes)))
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        seen: set[str] = set()
        for incident_id, note in notes:
            signal = _note_signal(
                incident_id,
                note,
                adapter_name=self.name,
                web_url=self.web_url,
                seen=seen,
            )
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_incident_ids(self, client: httpx.AsyncClient, *, limit: int) -> list[str]:
        if not self.query_params:
            return []
        incidents: list[str] = []
        offset = 0
        while len(incidents) < limit:
            page_limit = min(self.page_size, limit - len(incidents))
            body = await self._get(
                client,
                "/incidents",
                params={**self.query_params, "limit": page_limit, "offset": offset},
            )
            page = body.get("incidents") if isinstance(body, dict) else []
            if not isinstance(page, list) or not page:
                break
            for incident in page:
                if isinstance(incident, dict) and _optional(incident.get("id")):
                    incidents.append(str(incident["id"]))
            if not bool(body.get("more")):
                break
            offset = _next_offset(body, offset, page_limit)
        return incidents[:limit]

    async def _fetch_notes(
        self,
        client: httpx.AsyncClient,
        *,
        incident_id: str,
        limit: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        notes: list[tuple[str, dict[str, Any]]] = []
        offset = 0
        while len(notes) < limit:
            page_limit = min(self.page_size, limit - len(notes))
            body = await self._get(
                client,
                f"/incidents/{incident_id}/notes",
                params={"limit": page_limit, "offset": offset},
            )
            page = body.get("notes") if isinstance(body, dict) else []
            if not isinstance(page, list) or not page:
                break
            notes.extend((incident_id, note) for note in page if isinstance(note, dict))
            if not bool(body.get("more")):
                break
            offset = _next_offset(body, offset, page_limit)
        return notes[:limit]

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
            logger.warning("PagerDuty incident notes fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.pagerduty+json;version=2",
            "Authorization": f"Token token={self.api_token}",
            "User-Agent": "max-pagerduty-incident-notes-import/1",
        }
        if self.from_email:
            headers["From"] = self.from_email
        return headers


PagerDutyIncidentNoteAdapter = PagerDutyIncidentNotesAdapter


def _note_signal(
    incident_id: str,
    note: dict[str, Any],
    *,
    adapter_name: str,
    web_url: str | None,
    seen: set[str],
) -> Signal | None:
    note_id = _optional(note.get("id"))
    if not note_id:
        return None
    signal_id = f"pagerduty-note:{incident_id}:{note_id}"
    if signal_id in seen:
        return None
    seen.add(signal_id)

    author = _author(note.get("user"))
    created_at = _optional(note.get("created_at"))
    source_url = _source_url(note, incident_id=incident_id, web_url=web_url)
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FAILURE_DATA,
        source_adapter=adapter_name,
        title=f"PagerDuty incident {incident_id} note",
        content=_text(note.get("content"))[:1000],
        url=source_url,
        author=author,
        published_at=_parse_dt(created_at),
        tags=["pagerduty", "incident", "note"],
        credibility=0.7,
        metadata={
            "pagerduty_note_id": note_id,
            "pagerduty_incident_id": incident_id,
            "content": note.get("content"),
            "author": _author_metadata(note.get("user")),
            "created_at": created_at,
            "source_url": source_url,
            "raw": note,
        },
    )


def _author(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    return _optional(value.get("summary")) or _optional(value.get("name")) or _optional(value.get("email")) or _optional(value.get("id"))


def _author_metadata(value: object) -> dict[str, Any]:
    user = value if isinstance(value, dict) else {}
    return {
        "id": user.get("id"),
        "name": user.get("name") or user.get("summary"),
        "summary": user.get("summary"),
        "email": user.get("email"),
        "html_url": user.get("html_url"),
    }


def _source_url(note: dict[str, Any], *, incident_id: str, web_url: str | None) -> str:
    explicit = _optional(note.get("html_url")) or _optional(note.get("self"))
    if explicit:
        return explicit
    if web_url:
        return f"{web_url.rstrip('/')}/incidents/{incident_id}"
    return f"https://pagerduty.com/incidents/{incident_id}"


def _next_offset(body: dict[str, Any], offset: int, page_limit: int) -> int:
    if isinstance(body.get("offset"), int):
        return int(body["offset"]) + int(body.get("limit") or page_limit)
    return offset + page_limit


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _positive_int(value: object, *, default: int, maximum: int) -> int:
    return min(value, maximum) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
