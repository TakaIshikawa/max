"""Salesforce Opportunity import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)
DEFAULT_OPPORTUNITY_FIELDS = (
    "Id",
    "Name",
    "Description",
    "AccountId",
    "Account.Name",
    "Amount",
    "StageName",
    "Probability",
    "OwnerId",
    "Owner.Name",
    "CloseDate",
    "CreatedDate",
    "LastModifiedDate",
    "IsClosed",
)


class SalesforceOpportunitiesAdapter(SourceAdapter):
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
        return "salesforce_opportunities_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def query(self) -> str:
        fields = ", ".join(_fields(self._config.get("fields")) or DEFAULT_OPPORTUNITY_FIELDS)
        filters = _filters(self._config)
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        return f"SELECT {fields} FROM Opportunity{where} ORDER BY LastModifiedDate DESC"

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
                    opportunity_id = _text(record.get("Id"))
                    if not opportunity_id or opportunity_id in seen:
                        continue
                    seen.add(opportunity_id)
                    records.append(record)
                    if len(records) >= effective_limit:
                        break
                next_url = _optional(body.get("nextRecordsUrl"))
                path = next_url if next_url and len(records) < effective_limit else None
                params = None
        finally:
            if close_client:
                await client.aclose()
        return [_opportunity_signal(record, self.name, self.instance_url) for record in records[:effective_limit]]

    async def _get(self, client: httpx.AsyncClient, *, path: str, params: dict[str, Any] | None) -> dict[str, Any]:
        try:
            response = await client.get(f"{self.instance_url}{path}", headers={"Authorization": f"Bearer {self.access_token}"}, params=params)
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("Salesforce Opportunity fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}


SalesforceOpportunityAdapter = SalesforceOpportunitiesAdapter


def _opportunity_signal(record: dict[str, Any], adapter_name: str, instance_url: str) -> Signal:
    account = record.get("Account") if isinstance(record.get("Account"), dict) else {}
    owner = record.get("Owner") if isinstance(record.get("Owner"), dict) else {}
    opportunity_id = _text(record.get("Id"))
    name = _text(record.get("Name")) or opportunity_id
    account_name = _text(account.get("Name"))
    stage_name = _text(record.get("StageName"))
    amount = record.get("Amount")
    probability = record.get("Probability")
    close_date = _text(record.get("CloseDate"))
    record_url = f"{instance_url}/lightning/r/Opportunity/{opportunity_id}/view" if opportunity_id else instance_url
    context = [
        _text(record.get("Description")),
        f"Account: {account_name}" if account_name else "",
        f"Stage: {stage_name}" if stage_name else "",
        f"Amount: {amount}" if amount is not None else "",
        f"Probability: {probability}%" if probability is not None else "",
        f"Close date: {close_date}" if close_date else "",
    ]
    return Signal(
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=name,
        content="\n".join(item for item in context if item)[:1000],
        url=record_url,
        author=_text(owner.get("Name")) or None,
        published_at=_parse_dt(record.get("CreatedDate")),
        tags=sorted({"salesforce", "opportunity", stage_name} - {""})[:10],
        credibility=0.7,
        metadata={
            "salesforce_opportunity_id": record.get("Id"),
            "account_id": record.get("AccountId"),
            "account_name": account.get("Name"),
            "stage_name": record.get("StageName"),
            "amount": amount,
            "probability": probability,
            "owner_id": record.get("OwnerId"),
            "owner_name": owner.get("Name"),
            "close_date": record.get("CloseDate"),
            "created_at": record.get("CreatedDate"),
            "updated_at": record.get("LastModifiedDate"),
            "is_closed": record.get("IsClosed"),
        },
    )


def _filters(config: dict[str, Any]) -> list[str]:
    filters: list[str] = []
    stages = [_soql_string(value) for value in _list(config.get("stages"))]
    if stages:
        filters.append(f"StageName IN ({', '.join(stages)})")
    owner_ids = [_soql_string(value) for value in _list(config.get("owner_ids"))]
    if owner_ids:
        filters.append(f"OwnerId IN ({', '.join(owner_ids)})")
    close_date_from = _optional(config.get("close_date_from"))
    if close_date_from:
        filters.append(f"CloseDate >= {_soql_date(close_date_from)}")
    close_date_to = _optional(config.get("close_date_to"))
    if close_date_to:
        filters.append(f"CloseDate <= {_soql_date(close_date_to)}")
    min_amount = config.get("min_amount")
    if isinstance(min_amount, int | float) and not isinstance(min_amount, bool):
        filters.append(f"Amount >= {min_amount}")
    if config.get("include_closed") is not True:
        filters.append("IsClosed = false")
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


def _soql_date(value: str) -> str:
    return value[:10]


def _soql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


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
