"""Salesforce Lead import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_LEAD_FIELDS = (
    "Id",
    "Name",
    "FirstName",
    "LastName",
    "Company",
    "Title",
    "Description",
    "Status",
    "LeadSource",
    "OwnerId",
    "Owner.Name",
    "Industry",
    "Rating",
    "Email",
    "CreatedDate",
    "LastModifiedDate",
    "IsConverted",
)


class SalesforceLeadsAdapter(SourceAdapter):
    """Fetch Salesforce Lead records and convert them to market signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        instance_url: str | None = None,
        access_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.instance_url = (
            instance_url
            or _optional(self._config.get("instance_url"))
            or os.getenv("SALESFORCE_INSTANCE_URL")
            or ""
        ).rstrip("/")
        self.access_token = access_token if access_token is not None else os.getenv("SALESFORCE_ACCESS_TOKEN")
        self._client = client

    @property
    def name(self) -> str:
        return "salesforce_leads_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def query(self) -> str:
        fields = ", ".join(_fields(self._config.get("fields")) or DEFAULT_LEAD_FIELDS)
        filters = _filters(self._config)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        return f"SELECT {fields} FROM Lead{where} ORDER BY LastModifiedDate DESC"

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
            seen: set[str] = set()
            path: str | None = "/services/data/v60.0/query"
            params: dict[str, Any] | None = {"q": self.query}
            while path and len(records) < effective_limit:
                body = await self._get(client, path=path, params=params)
                page = body.get("records") if isinstance(body.get("records"), list) else []
                for record in page:
                    if not isinstance(record, dict):
                        continue
                    lead_id = _text(record.get("Id"))
                    if not lead_id or lead_id in seen:
                        continue
                    seen.add(lead_id)
                    records.append(record)
                    if len(records) >= effective_limit:
                        break
                next_url = _optional(body.get("nextRecordsUrl"))
                path = next_url if next_url and len(records) < effective_limit else None
                params = None
        finally:
            if close_client:
                await client.aclose()
        return [_lead_signal(record, self.name, self.instance_url) for record in records[:effective_limit]]

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        path: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.instance_url}{path}",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Salesforce Lead fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


SalesforceLeadAdapter = SalesforceLeadsAdapter


def _lead_signal(record: dict[str, Any], adapter_name: str, instance_url: str) -> Signal:
    owner = _dict(record.get("Owner"))
    lead_id = _text(record.get("Id"))
    name = _text(record.get("Name")) or " ".join(
        part for part in [_text(record.get("FirstName")), _text(record.get("LastName"))] if part
    )
    company = _text(record.get("Company"))
    status = _text(record.get("Status"))
    lead_source = _text(record.get("LeadSource"))
    industry = _text(record.get("Industry"))
    rating = _text(record.get("Rating"))
    record_url = f"{instance_url}/lightning/r/Lead/{lead_id}/view" if lead_id else instance_url
    context = [
        _text(record.get("Description")),
        f"Company: {company}" if company else "",
        f"Title: {_text(record.get('Title'))}" if _text(record.get("Title")) else "",
        f"Status: {status}" if status else "",
        f"Lead source: {lead_source}" if lead_source else "",
        f"Industry: {industry}" if industry else "",
        f"Rating: {rating}" if rating else "",
    ]
    return Signal(
        id=f"salesforce-lead:{lead_id}" if lead_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=name or company or lead_id,
        content="\n".join(item for item in context if item)[:1000],
        url=record_url,
        author=_text(owner.get("Name")) or None,
        published_at=_parse_dt(record.get("CreatedDate")),
        tags=sorted({"salesforce", "lead", status, lead_source, industry, rating} - {""})[:10],
        credibility=0.7,
        metadata={
            "salesforce_lead_id": record.get("Id"),
            "name": record.get("Name"),
            "first_name": record.get("FirstName"),
            "last_name": record.get("LastName"),
            "company": record.get("Company"),
            "title": record.get("Title"),
            "status": record.get("Status"),
            "lead_source": record.get("LeadSource"),
            "owner_id": record.get("OwnerId"),
            "owner_name": owner.get("Name"),
            "industry": record.get("Industry"),
            "rating": record.get("Rating"),
            "email": record.get("Email"),
            "created_at": record.get("CreatedDate"),
            "updated_at": record.get("LastModifiedDate"),
            "is_converted": record.get("IsConverted"),
        },
    )


def _filters(config: dict[str, Any]) -> list[str]:
    filters: list[str] = []
    statuses = [_soql_string(value) for value in _list(config.get("statuses"))]
    if statuses:
        filters.append(f"Status IN ({', '.join(statuses)})")
    sources = [_soql_string(value) for value in _list(config.get("lead_sources"))]
    if sources:
        filters.append(f"LeadSource IN ({', '.join(sources)})")
    owner_ids = [_soql_string(value) for value in _list(config.get("owner_ids"))]
    if owner_ids:
        filters.append(f"OwnerId IN ({', '.join(owner_ids)})")
    industries = [_soql_string(value) for value in _list(config.get("industries"))]
    if industries:
        filters.append(f"Industry IN ({', '.join(industries)})")
    ratings = [_soql_string(value) for value in _list(config.get("ratings"))]
    if ratings:
        filters.append(f"Rating IN ({', '.join(ratings)})")
    created_after = _optional(config.get("created_after"))
    if created_after:
        filters.append(f"CreatedDate >= {_soql_datetime(created_after)}")
    if config.get("include_converted") is not True:
        filters.append("IsConverted = false")
    return filters


def _fields(value: object) -> tuple[str, ...]:
    fields = _list(value)
    return tuple(field for field in fields if _valid_field(field))


def _list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return []


def _valid_field(value: str) -> bool:
    return all(part.replace("_", "").isalnum() for part in value.split("."))


def _soql_datetime(value: str) -> str:
    return value


def _soql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
