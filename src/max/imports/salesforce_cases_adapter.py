"""Salesforce Case import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_CASE_QUERY = "SELECT Id, CaseNumber, Subject, Description, Status, Priority, Origin, Account.Name, Contact.Name, Owner.Name, CreatedDate, LastModifiedDate FROM Case ORDER BY LastModifiedDate DESC"


class SalesforceCasesAdapter(SourceAdapter):
    def __init__(
        self,
        config: dict | None = None,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.instance_url = (instance_url or _optional(self._config.get("instance_url")) or os.getenv("SALESFORCE_INSTANCE_URL") or "").rstrip("/")
        self.access_token = access_token if access_token is not None else os.getenv("SALESFORCE_ACCESS_TOKEN")
        self._client = client

    @property
    def name(self) -> str:
        return "salesforce_cases_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.ROADMAP.value

    @property
    def query(self) -> str:
        return _optional(self._config.get("query")) or DEFAULT_CASE_QUERY

    @property
    def limit(self) -> int | None:
        value = self._config.get("limit")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        return None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, self.limit) if self.limit else limit
        if effective_limit <= 0 or not (self.instance_url and self.access_token):
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            records: list[dict[str, Any]] = []
            path: str | None = "/services/data/v60.0/query"
            params: dict[str, Any] | None = {"q": self.query}
            while path and len(records) < effective_limit:
                body = await self._get(client, path=path, params=params)
                page = body.get("records") if isinstance(body.get("records"), list) else []
                records.extend(page)
                next_url = _optional(body.get("nextRecordsUrl"))
                path = next_url if next_url and len(records) < effective_limit else None
                params = None
        finally:
            if close_client:
                await client.aclose()
        return [_case_signal(record, self.name, self.instance_url) for record in records[:effective_limit] if isinstance(record, dict)]

    async def _get(self, client: httpx.AsyncClient, *, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(f"{self.instance_url}{path}", headers={"Authorization": f"Bearer {self.access_token}"}, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Salesforce Case fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


SalesforceCaseAdapter = SalesforceCasesAdapter


def _case_signal(record: dict[str, Any], adapter_name: str, instance_url: str) -> Signal:
    account = record.get("Account") if isinstance(record.get("Account"), dict) else {}
    contact = record.get("Contact") if isinstance(record.get("Contact"), dict) else {}
    owner = record.get("Owner") if isinstance(record.get("Owner"), dict) else {}
    case_id = _text(record.get("Id"))
    record_url = f"{instance_url}/lightning/r/Case/{case_id}/view" if case_id else instance_url
    return Signal(
        source_type=SignalSourceType.ROADMAP,
        source_adapter=adapter_name,
        title=_text(record.get("Subject")) or _text(record.get("CaseNumber")) or case_id,
        content=_text(record.get("Description"))[:1000],
        url=record_url,
        author=_text(owner.get("Name")) or None,
        published_at=_parse_dt(record.get("CreatedDate")),
        tags=sorted({"salesforce", _text(record.get("Status")), _text(record.get("Priority")), _text(record.get("Origin"))} - {""})[:10],
        credibility=0.7,
        metadata={
            "salesforce_case_id": record.get("Id"),
            "case_number": record.get("CaseNumber"),
            "status": record.get("Status"),
            "priority": record.get("Priority"),
            "origin": record.get("Origin"),
            "account": account.get("Name"),
            "contact": contact.get("Name"),
            "owner": owner.get("Name"),
            "created_date": record.get("CreatedDate"),
            "last_modified_date": record.get("LastModifiedDate"),
        },
    )


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
