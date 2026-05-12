"""HubSpot company notes import adapter."""

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
DEFAULT_NOTE_PROPERTIES = [
    "hs_note_body",
    "hs_timestamp",
    "hubspot_owner_id",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotCompanyNotesAdapter(SourceAdapter):
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
            else (
                _optional(self._config.get("token"))
                or os.getenv("HUBSPOT_ACCESS_TOKEN")
                or os.getenv("HUBSPOT_TOKEN")
            )
        )
        self.api_url = (
            api_url
            or _optional(self._config.get("api_url"))
            or os.getenv("HUBSPOT_API_URL")
            or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_company_notes_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def company_ids(self) -> list[str]:
        return _strings(
            self._config.get("company_ids")
            or self._config.get("companies")
            or self._config.get("company_id")
        )

    @property
    def association_type_ids(self) -> set[str]:
        return set(
            _strings(
                self._config.get("association_type_ids")
                or self._config.get("association_type_id")
                or self._config.get("association_types")
                or self._config.get("association_type")
            )
        )

    @property
    def created_after(self) -> datetime | None:
        return _parse_dt(self._config.get("created_after"))

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_NOTE_PROPERTIES

    @property
    def association_page_limit(self) -> int:
        return _positive_int(self._config.get("association_page_limit"), default=100, maximum=500)

    @property
    def per_company_limit(self) -> int | None:
        value = self._config.get("per_company_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.company_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            for company_id in self.company_ids:
                if len(signals) >= limit:
                    break
                company_limit = min(self.per_company_limit or limit, limit - len(signals))
                note_ids = await self._fetch_note_ids(
                    client,
                    company_id=company_id,
                    limit=company_limit,
                )
                for note_id in note_ids:
                    if len(signals) >= limit:
                        break
                    note = await self._fetch_note(client, note_id=note_id)
                    if not note:
                        continue
                    signal = _note_signal(note, company_id, self.name)
                    if self.created_after and _before(signal.published_at, self.created_after):
                        continue
                    signals.append(signal)
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_note_ids(
        self,
        client: httpx.AsyncClient,
        *,
        company_id: str,
        limit: int,
    ) -> list[str]:
        note_ids: list[str] = []
        after: str | None = None
        while len(note_ids) < limit:
            body = await self._get(
                client,
                f"{self.api_url}/crm/v4/objects/companies/{company_id}/associations/notes",
                params={
                    "limit": min(self.association_page_limit, limit - len(note_ids)),
                    **({"after": after} if after else {}),
                },
            )
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            for item in results:
                note_id = _association_note_id(item, self.association_type_ids)
                if note_id and note_id not in note_ids:
                    note_ids.append(note_id)
                    if len(note_ids) >= limit:
                        break
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return note_ids[:limit]

    async def _fetch_note(
        self,
        client: httpx.AsyncClient,
        *,
        note_id: str,
    ) -> dict[str, Any]:
        body = await self._get(
            client,
            f"{self.api_url}/crm/v3/objects/notes/{note_id}",
            params={"properties": self.properties},
        )
        return body if isinstance(body, dict) else {}

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any],
    ) -> object:
        try:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/json",
                    "User-Agent": "max-hubspot-company-notes-import/1",
                },
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            logger.warning("HubSpot company notes fetch failed for %s", url, exc_info=True)
            return {}


HubSpotCompanyNoteAdapter = HubSpotCompanyNotesAdapter


def _note_signal(note: dict[str, Any], company_id: str, adapter_name: str) -> Signal:
    props = note.get("properties") if isinstance(note.get("properties"), dict) else {}
    note_id = _text(note.get("id"))
    body = _text(props.get("hs_note_body"))
    owner = _text(props.get("hubspot_owner_id"))
    created_at = props.get("createdate") or note.get("createdAt") or props.get("hs_timestamp")
    updated_at = props.get("hs_lastmodifieddate") or note.get("updatedAt")
    return Signal(
        id=f"hubspot-company-note:{company_id}:{note_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"HubSpot company {company_id} note",
        content=body or f"HubSpot note {note_id}",
        url=_note_url(note, company_id),
        author=owner or None,
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "company", "note"} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "customer",
            "hubspot_company_id": company_id,
            "company_id": company_id,
            "hubspot_note_id": note.get("id"),
            "note_id": note.get("id"),
            "body": body or None,
            "owner_id": owner or None,
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": note.get("archived"),
            "properties": props,
            "raw": note,
        },
    )


def _association_note_id(item: object, association_type_ids: set[str]) -> str | None:
    if not isinstance(item, dict):
        return None
    if association_type_ids and not _matches_association_type(item, association_type_ids):
        return None
    return _optional(item.get("toObjectId") or item.get("id"))


def _matches_association_type(item: dict[str, Any], association_type_ids: set[str]) -> bool:
    for key in ("typeId", "associationTypeId"):
        value = _text(item.get(key))
        if value in association_type_ids:
            return True
    association_types = item.get("associationTypes")
    if not isinstance(association_types, list):
        return False
    for association_type in association_types:
        if not isinstance(association_type, dict):
            continue
        values = {
            _text(association_type.get("typeId")),
            _text(association_type.get("associationTypeId")),
            _text(association_type.get("label")),
            _text(association_type.get("category")),
        }
        if values & association_type_ids:
            return True
    return False


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _note_url(note: dict[str, Any], company_id: str) -> str:
    if _text(note.get("url")):
        return _text(note.get("url"))
    return f"https://app.hubspot.com/contacts/company/{company_id}"


def _before(value: datetime | None, threshold: datetime) -> bool:
    if value is None:
        return False
    compare = value
    target = threshold
    if compare.tzinfo is None and target.tzinfo is not None:
        compare = compare.replace(tzinfo=target.tzinfo)
    if target.tzinfo is None and compare.tzinfo is not None:
        target = target.replace(tzinfo=compare.tzinfo)
    return compare < target


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
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    for item in value:
        if isinstance(item, bool):
            continue
        text = _text(item)
        if text:
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
