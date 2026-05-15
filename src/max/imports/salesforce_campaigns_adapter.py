"""Salesforce Campaign import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_CAMPAIGN_FIELDS = (
    "Id",
    "Name",
    "Type",
    "Status",
    "Description",
    "BudgetedCost",
    "ActualCost",
    "ExpectedRevenue",
    "ExpectedResponse",
    "StartDate",
    "EndDate",
    "ParentId",
    "Parent.Name",
    "OwnerId",
    "Owner.Name",
    "CreatedDate",
    "LastModifiedDate",
    "IsActive",
)


class SalesforceCampaignsAdapter(SourceAdapter):
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
        self.access_token = access_token if access_token is not None else (_optional(self._config.get("access_token")) or os.getenv("SALESFORCE_ACCESS_TOKEN"))
        self._client = client

    @property
    def name(self) -> str:
        return "salesforce_campaigns_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def api_version(self) -> str:
        return _optional(self._config.get("api_version")) or "v60.0"

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size"), default=200, maximum=2000)

    @property
    def query(self) -> str:
        fields = ", ".join(_fields(self._config.get("fields")) or DEFAULT_CAMPAIGN_FIELDS)
        filters = _filters(self._config)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        return f"SELECT {fields} FROM Campaign{where} ORDER BY LastModifiedDate DESC"

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
            path: str | None = f"/services/data/{self.api_version}/query"
            params: dict[str, Any] | None = {"q": self.query}
            while path and len(records) < effective_limit:
                body = await self._get(client, path=path, params=params)
                page = body.get("records") if isinstance(body.get("records"), list) else []
                for record in page:
                    if not isinstance(record, dict):
                        continue
                    campaign_id = _text(record.get("Id"))
                    if not campaign_id or campaign_id in seen:
                        continue
                    seen.add(campaign_id)
                    records.append(record)
                    if len(records) >= effective_limit:
                        break
                next_url = _optional(body.get("nextRecordsUrl"))
                path = next_url if next_url and len(records) < effective_limit else None
                params = None
        finally:
            if close_client:
                await client.aclose()
        return [_campaign_signal(record, self.name, self.instance_url) for record in records[:effective_limit]]

    async def _get(self, client: httpx.AsyncClient, *, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.instance_url}{path}",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/json",
                    "Sforce-Query-Options": f"batchSize={self.page_size}",
                },
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Salesforce Campaign fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


SalesforceCampaignAdapter = SalesforceCampaignsAdapter


def _campaign_signal(record: dict[str, Any], adapter_name: str, instance_url: str) -> Signal:
    parent = record.get("Parent") if isinstance(record.get("Parent"), dict) else {}
    owner = record.get("Owner") if isinstance(record.get("Owner"), dict) else {}
    campaign_id = _text(record.get("Id"))
    name = _text(record.get("Name")) or campaign_id
    campaign_type = _text(record.get("Type"))
    status = _text(record.get("Status"))
    record_url = f"{instance_url}/lightning/r/Campaign/{campaign_id}/view" if campaign_id else instance_url
    content = _content(
        description=_text(record.get("Description")),
        campaign_type=campaign_type,
        status=status,
        budgeted_cost=record.get("BudgetedCost"),
        actual_cost=record.get("ActualCost"),
        expected_revenue=record.get("ExpectedRevenue"),
        start_date=record.get("StartDate"),
        end_date=record.get("EndDate"),
        parent_name=_text(parent.get("Name")),
    )
    return Signal(
        id=f"salesforce-campaign:{campaign_id}" if campaign_id else None,
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=name,
        content=content[:1000],
        url=record_url,
        author=_text(owner.get("Name")) or None,
        published_at=_parse_dt(record.get("CreatedDate")),
        tags=sorted({"salesforce", "campaign", campaign_type, status} - {""})[:10],
        credibility=0.7,
        metadata={
            "salesforce_campaign_id": record.get("Id"),
            "name": record.get("Name"),
            "type": record.get("Type"),
            "status": record.get("Status"),
            "budgeted_cost": record.get("BudgetedCost"),
            "actual_cost": record.get("ActualCost"),
            "expected_revenue": record.get("ExpectedRevenue"),
            "expected_response": record.get("ExpectedResponse"),
            "start_date": record.get("StartDate"),
            "end_date": record.get("EndDate"),
            "parent_id": record.get("ParentId"),
            "parent_name": parent.get("Name"),
            "description": record.get("Description"),
            "owner_id": record.get("OwnerId"),
            "owner_name": owner.get("Name"),
            "created_at": record.get("CreatedDate"),
            "updated_at": record.get("LastModifiedDate"),
            "is_active": record.get("IsActive"),
            "raw": record,
        },
    )


def _content(*, description: str, campaign_type: str, status: str, budgeted_cost: object, actual_cost: object, expected_revenue: object, start_date: object, end_date: object, parent_name: str) -> str:
    context = [
        description,
        f"Type: {campaign_type}" if campaign_type else "",
        f"Status: {status}" if status else "",
        f"Budgeted cost: {budgeted_cost}" if budgeted_cost is not None else "",
        f"Actual cost: {actual_cost}" if actual_cost is not None else "",
        f"Expected revenue: {expected_revenue}" if expected_revenue is not None else "",
        f"Start date: {start_date}" if start_date else "",
        f"End date: {end_date}" if end_date else "",
        f"Parent campaign: {parent_name}" if parent_name else "",
    ]
    return "\n".join(item for item in context if item)


def _filters(config: dict[str, Any]) -> list[str]:
    filters: list[str] = []
    statuses = [_soql_string(value) for value in _list(config.get("statuses") or config.get("status"))]
    if statuses:
        filters.append(f"Status IN ({', '.join(statuses)})")
    campaign_types = [_soql_string(value) for value in _list(config.get("types") or config.get("type"))]
    if campaign_types:
        filters.append(f"Type IN ({', '.join(campaign_types)})")
    if config.get("active_only") is True:
        filters.append("IsActive = true")
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


def _soql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    for candidate in (value, value.replace("+0000", "+00:00")):
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            continue
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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
