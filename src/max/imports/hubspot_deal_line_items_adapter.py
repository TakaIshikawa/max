"""HubSpot deal line items import adapter."""

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
DEFAULT_LINE_ITEM_PROPERTIES = [
    "name",
    "quantity",
    "price",
    "amount",
    "hs_line_item_currency_code",
    "hs_sku",
    "hs_product_id",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotDealLineItemsAdapter(SourceAdapter):
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
            api_url or _optional(self._config.get("api_url")) or os.getenv("HUBSPOT_API_URL") or HUBSPOT_API
        ).rstrip("/")
        self._client = client

    @property
    def name(self) -> str:
        return "hubspot_deal_line_items_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def deal_ids(self) -> list[str]:
        return _strings(
            self._config.get("deal_ids")
            or self._config.get("deals")
            or self._config.get("deal_id")
        )

    @property
    def properties(self) -> list[str]:
        configured = _strings(self._config.get("properties"))
        return configured or DEFAULT_LINE_ITEM_PROPERTIES

    @property
    def association_page_limit(self) -> int:
        return _positive_int(
            self._config.get("association_page_limit") or self._config.get("page_size"),
            default=100,
            maximum=500,
        )

    @property
    def per_deal_limit(self) -> int | None:
        value = self._config.get("per_deal_limit")
        if value is None:
            return None
        return _positive_int(value, default=0, maximum=10_000) or None

    @property
    def association_type_ids(self) -> set[str]:
        return set(_strings(self._config.get("association_type_ids") or self._config.get("association_type_id")))

    @property
    def created_after(self) -> datetime | None:
        return _parse_dt(self._config.get("created_after"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token or not self.deal_ids:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            signals: list[Signal] = []
            seen_line_items: set[str] = set()
            for deal_id in self.deal_ids:
                if len(signals) >= limit:
                    break
                deal_limit = min(self.per_deal_limit or limit, limit - len(signals))
                associations = await self._fetch_associations(client, deal_id=deal_id, limit=deal_limit)
                for association in associations:
                    if len(signals) >= limit:
                        break
                    line_item_id = _association_line_item_id(association)
                    if not line_item_id or line_item_id in seen_line_items:
                        continue
                    seen_line_items.add(line_item_id)
                    line_item = await self._fetch_line_item(client, line_item_id=line_item_id)
                    if not line_item or not _created_after(line_item, self.created_after):
                        continue
                    signals.append(
                        _line_item_signal(
                            line_item,
                            deal_id=deal_id,
                            association=association,
                            adapter_name=self.name,
                        )
                    )
            return signals[:limit]
        finally:
            if close_client:
                await client.aclose()

    async def _fetch_associations(
        self,
        client: httpx.AsyncClient,
        *,
        deal_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        associations: list[dict[str, Any]] = []
        after: str | None = None
        while len(associations) < limit:
            page_limit = min(self.association_page_limit, limit - len(associations))
            body = await self._get_association_page(client, deal_id=deal_id, limit=page_limit, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            for item in results:
                if not isinstance(item, dict):
                    continue
                if self.association_type_ids and not self.association_type_ids.intersection(_association_type_ids(item)):
                    continue
                associations.append(item)
                if len(associations) >= limit:
                    break
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return associations[:limit]

    async def _get_association_page(
        self,
        client: httpx.AsyncClient,
        *,
        deal_id: str,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        try:
            response = await client.get(
                f"{self.api_url}/crm/v4/objects/deals/{deal_id}/associations/line_items",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot deal line item associations fetch failed for deal %s", deal_id, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    async def _fetch_line_item(self, client: httpx.AsyncClient, *, line_item_id: str) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/line_items/{line_item_id}",
                headers=self._headers,
                params={"properties": self.properties},
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot line item fetch failed for %s", line_item_id, exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "max-hubspot-deal-line-items-import/1",
        }


HubSpotDealLineItemAdapter = HubSpotDealLineItemsAdapter


def _line_item_signal(
    line_item: dict[str, Any],
    *,
    deal_id: str,
    association: dict[str, Any],
    adapter_name: str,
) -> Signal:
    props = line_item.get("properties") if isinstance(line_item.get("properties"), dict) else {}
    line_item_id = _text(line_item.get("id")) or _text(props.get("hs_object_id")) or _association_line_item_id(association)
    name = _text(props.get("name")) or f"HubSpot line item {line_item_id}"
    quantity = _number(props.get("quantity"))
    price = _number(props.get("price"))
    amount = _number(props.get("amount"))
    currency = _text(props.get("hs_line_item_currency_code") or props.get("currency"))
    sku = _text(props.get("hs_sku") or props.get("sku"))
    product_id = _text(props.get("hs_product_id") or props.get("product_id"))
    return Signal(
        id=f"hubspot-deal-line-item:{deal_id}:{line_item_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=name,
        content=_content(name=name, quantity=quantity, amount=amount, currency=currency),
        url=_line_item_url(line_item, line_item_id=line_item_id),
        author=_text(props.get("hubspot_owner_id")) or None,
        published_at=_parse_dt(props.get("createdate") or line_item.get("createdAt")),
        tags=sorted({"hubspot", "deal-line-item", currency, sku, product_id} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_deal_id": deal_id,
            "deal_id": deal_id,
            "hubspot_line_item_id": line_item_id,
            "line_item_id": line_item_id,
            "name": name,
            "quantity": quantity,
            "price": price,
            "amount": amount,
            "currency": currency or None,
            "sku": sku or None,
            "product_id": product_id or None,
            "created_at": props.get("createdate") or line_item.get("createdAt"),
            "updated_at": props.get("hs_lastmodifieddate") or line_item.get("updatedAt"),
            "association": association,
            "association_type_ids": sorted(_association_type_ids(association)),
            "url": _line_item_url(line_item, line_item_id=line_item_id),
            "properties": props,
            "raw": line_item,
        },
    )


def _content(*, name: str, quantity: float | int | None, amount: float | int | None, currency: str) -> str:
    parts = [name]
    if quantity is not None:
        parts.append(f"quantity {quantity:g}")
    if amount is not None:
        money = f"{amount:g} {currency}".strip()
        parts.append(f"amount {money}")
    return "; ".join(parts)


def _created_after(line_item: dict[str, Any], created_after: datetime | None) -> bool:
    if created_after is None:
        return True
    props = line_item.get("properties") if isinstance(line_item.get("properties"), dict) else {}
    created_at = _parse_dt(props.get("createdate") or line_item.get("createdAt"))
    return created_at is not None and created_at > created_after


def _association_line_item_id(association: dict[str, Any]) -> str:
    to_object_id = association.get("toObjectId")
    if to_object_id is None:
        to_object_id = association.get("id")
    return _text(to_object_id)


def _association_type_ids(association: dict[str, Any]) -> set[str]:
    type_ids: set[str] = set()
    for key in ("associationTypeId", "typeId"):
        value = _optional(association.get(key))
        if value:
            type_ids.add(value)
    association_types = association.get("associationTypes")
    if isinstance(association_types, list):
        for item in association_types:
            if isinstance(item, dict):
                value = _optional(item.get("typeId") or item.get("associationTypeId"))
                if value:
                    type_ids.add(value)
    return type_ids


def _line_item_url(line_item: dict[str, Any], *, line_item_id: str) -> str:
    if _text(line_item.get("url")):
        return _text(line_item.get("url"))
    return f"https://app.hubspot.com/contacts/line-item/{line_item_id}" if line_item_id else ""


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


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


def _number(value: object) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _strings(value: object) -> list[str]:
    if isinstance(value, (str, int)) and not isinstance(value, bool):
        value = [value]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, dict):
            item = item.get("id") or item.get("dealId") or item.get("deal_id")
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
