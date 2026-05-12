"""HubSpot deal import adapter."""

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


class HubSpotAdapter(SourceAdapter):
    def __init__(self, config: dict | None = None, *, token: str | None = None, api_url: str = HUBSPOT_API, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config)
        self.token = token if token is not None else os.getenv("HUBSPOT_ACCESS_TOKEN")
        self.api_url = api_url.rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def pipeline_ids(self) -> list[str]:
        return _strings(self._config.get("pipeline_ids"))

    @property
    def stage_ids(self) -> list[str]:
        return _strings(self._config.get("stage_ids"))

    @property
    def owners(self) -> list[str]:
        return _strings(self._config.get("owners"))

    @property
    def min_amount(self) -> float | None:
        value = self._config.get("min_amount")
        return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None

    @property
    def updated_since(self) -> str | None:
        value = self._config.get("updated_since")
        return value if isinstance(value, str) and value else None

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []
        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            try:
                response = await client.post(
                    f"{self.api_url}/crm/v3/objects/deals/search",
                    headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                    json={"limit": min(limit, 100), "properties": ["dealname", "amount", "dealstage", "pipeline", "closedate", "hubspot_owner_id", "createdate", "hs_lastmodifieddate"], "filterGroups": [{"filters": self._filters()}]},
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("HubSpot deal fetch failed", exc_info=True)
                return []
        finally:
            if close_client:
                await client.aclose()
        return [_deal_signal(deal, self.name) for deal in (body.get("results") or [])[:limit] if isinstance(deal, dict)]

    def _filters(self) -> list[dict[str, Any]]:
        filters: list[dict[str, Any]] = []
        if self.pipeline_ids:
            filters.append({"propertyName": "pipeline", "operator": "IN", "values": self.pipeline_ids})
        if self.stage_ids:
            filters.append({"propertyName": "dealstage", "operator": "IN", "values": self.stage_ids})
        if self.owners:
            filters.append({"propertyName": "hubspot_owner_id", "operator": "IN", "values": self.owners})
        if self.min_amount is not None:
            filters.append({"propertyName": "amount", "operator": "GTE", "value": str(self.min_amount)})
        if self.updated_since:
            filters.append({"propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": self.updated_since})
        return filters


HubSpotDealAdapter = HubSpotAdapter


def _deal_signal(deal: dict[str, Any], adapter_name: str) -> Signal:
    props = deal.get("properties") if isinstance(deal.get("properties"), dict) else {}
    amount = _number(props.get("amount"))
    associations = deal.get("associations") if isinstance(deal.get("associations"), dict) else {}
    companies = (((associations.get("companies") or {}).get("results")) or [])
    return Signal(
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=_text(props.get("dealname")) or _text(deal.get("id")),
        content=f"HubSpot deal stage: {_text(props.get('dealstage'))}",
        url=_text(deal.get("url")),
        author=_text(props.get("hubspot_owner_id")) or None,
        published_at=_parse_dt(props.get("createdate")),
        tags=sorted({"hubspot", _text(props.get("pipeline")), _text(props.get("dealstage"))} - {""})[:10],
        credibility=0.7,
        metadata={"hubspot_deal_id": deal.get("id"), "amount": amount, "stage": props.get("dealstage"), "pipeline": props.get("pipeline"), "owner_id": props.get("hubspot_owner_id"), "close_date": props.get("closedate"), "company_ids": [item.get("id") for item in companies if isinstance(item, dict)], "created_at": props.get("createdate"), "updated_at": props.get("hs_lastmodifieddate")},
    )


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _number(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
