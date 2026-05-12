"""Airtable record import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
AIRTABLE_API = "https://api.airtable.com/v0"


class AirtableAdapter(SourceAdapter):
    def __init__(self, config: dict | None = None, *, token: str | None = None, api_url: str = AIRTABLE_API, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self.token = token if token is not None else (os.getenv("AIRTABLE_API_KEY") or os.getenv("AIRTABLE_ACCESS_TOKEN"))
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "airtable_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def base_id(self) -> str | None:
        return _optional(self._config.get("base_id"))

    @property
    def table_name(self) -> str | None:
        return _optional(self._config.get("table_name"))

    @property
    def view(self) -> str | None:
        return _optional(self._config.get("view"))

    @property
    def formula(self) -> str | None:
        return _optional(self._config.get("formula"))

    @property
    def title_field(self) -> str:
        return _optional(self._config.get("title_field")) or "Name"

    @property
    def description_field(self) -> str:
        return _optional(self._config.get("description_field")) or "Description"

    @property
    def status_field(self) -> str:
        return _optional(self._config.get("status_field")) or "Status"

    @property
    def owner_field(self) -> str:
        return _optional(self._config.get("owner_field")) or "Owner"

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not (self.token and self.base_id and self.table_name):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            records: list[dict[str, Any]] = []
            offset: str | None = None
            while len(records) < limit:
                page, offset = await self._get_page(client, offset=offset, limit=limit - len(records))
                records.extend(page)
                if not offset:
                    break
        finally:
            if close_client:
                await client.aclose()
        return [_record_signal(record, self) for record in records[:limit] if isinstance(record, dict)]

    async def _get_page(self, client: httpx.AsyncClient, *, offset: str | None, limit: int) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"pageSize": min(limit, 100)}
        if self.view:
            params["view"] = self.view
        if self.formula:
            params["filterByFormula"] = self.formula
        if offset:
            params["offset"] = offset
        try:
            response = await client.get(f"{self.api_url}/{self.base_id}/{quote(self.table_name or '', safe='')}", headers={"Authorization": f"Bearer {self.token}"}, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.warning("Airtable record fetch failed", exc_info=True)
            return [], None
        return data.get("records") if isinstance(data.get("records"), list) else [], _optional(data.get("offset"))


AirtableRecordAdapter = AirtableAdapter


def _record_signal(record: dict[str, Any], adapter: AirtableAdapter) -> Signal:
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
    title = _text(fields.get(adapter.title_field) or record.get("id"))
    status = _text(fields.get(adapter.status_field))
    owner = _text(fields.get(adapter.owner_field))
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter.name,
        title=title,
        content=_text(fields.get(adapter.description_field))[:1000],
        url=_text(record.get("url")),
        author=owner or None,
        published_at=_parse_dt(record.get("createdTime")),
        tags=sorted({"airtable", status} - {""})[:10],
        credibility=0.6,
        metadata={"airtable_record_id": record.get("id"), "base_id": adapter.base_id, "table_name": adapter.table_name, "status": status or None, "owner": owner or None, "created_time": record.get("createdTime"), "last_modified_time": fields.get("Last Modified") or fields.get("Last modified time"), "fields": fields},
    )


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
