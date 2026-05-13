"""HubSpot products import adapter."""

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
DEFAULT_PRODUCT_PROPERTIES = [
    "name",
    "price",
    "hs_sku",
    "sku",
    "hs_product_type",
    "description",
    "createdate",
    "hs_lastmodifieddate",
]


class HubSpotProductsAdapter(SourceAdapter):
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
        return "hubspot_products_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def properties(self) -> list[str]:
        return _strings(self._config.get("properties")) or DEFAULT_PRODUCT_PROPERTIES

    @property
    def archived(self) -> bool | None:
        return _bool(self._config.get("archived"))

    @property
    def after(self) -> str | None:
        return _optional(self._config.get("after"))

    @property
    def page_size(self) -> int:
        return _positive_int(
            self._config.get("page_size") or self._config.get("per_page") or self._config.get("limit"),
            default=100,
            maximum=100,
        )

    @property
    def created_after(self) -> datetime | None:
        return _parse_dt(self._config.get("created_after"))

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.token:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            products = await self._fetch_products(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        return [
            _product_signal(product, self.name)
            for product in products[:limit]
            if isinstance(product, dict)
        ]

    async def _fetch_products(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        products: list[dict[str, Any]] = []
        after = self.after
        while len(products) < limit:
            page_limit = min(self.page_size, limit - len(products))
            body = await self._get_products(client, limit=page_limit, after=after)
            results = body.get("results") if isinstance(body, dict) else []
            if not isinstance(results, list) or not results:
                break
            for item in results:
                if not isinstance(item, dict) or not _created_after(item, self.created_after):
                    continue
                products.append(item)
                if len(products) >= limit:
                    break
            next_after = _next_after(body)
            if not next_after:
                break
            after = next_after
        return products[:limit]

    async def _get_products(
        self,
        client: httpx.AsyncClient,
        *,
        limit: int,
        after: str | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "properties": self.properties}
        if after:
            params["after"] = after
        if self.archived is not None:
            params["archived"] = str(self.archived).lower()
        try:
            response = await client.get(
                f"{self.api_url}/crm/v3/objects/products",
                headers=self._headers,
                params=params,
            )
            response.raise_for_status()
            body = response.json()
        except Exception:
            logger.warning("HubSpot products fetch failed", exc_info=True)
            return {}
        return body if isinstance(body, dict) else {}

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "max-hubspot-products-import/1",
        }


HubSpotProductAdapter = HubSpotProductsAdapter


def _product_signal(product: dict[str, Any], adapter_name: str) -> Signal:
    props = product.get("properties") if isinstance(product.get("properties"), dict) else {}
    product_id = _text(product.get("id")) or _text(props.get("hs_object_id"))
    name = _text(props.get("name")) or f"HubSpot product {product_id}"
    price = _number(props.get("price"))
    sku = _text(props.get("hs_sku") or props.get("sku"))
    product_type = _text(props.get("hs_product_type"))
    created_at = props.get("createdate") or product.get("createdAt")
    updated_at = props.get("hs_lastmodifieddate") or product.get("updatedAt")
    return Signal(
        id=f"hubspot-product:{product_id}" if product_id else "",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=name,
        content=_content(name=name, price=price, sku=sku, product_type=product_type),
        url=_product_url(product, product_id=product_id),
        published_at=_parse_dt(created_at),
        tags=sorted({"hubspot", "product", sku, product_type} - {""})[:10],
        credibility=0.68,
        metadata={
            "signal_role": "market",
            "hubspot_product_id": product_id,
            "product_id": product_id,
            "name": name,
            "price": price,
            "sku": sku or None,
            "hs_product_type": product_type or None,
            "createdate": props.get("createdate"),
            "hs_lastmodifieddate": props.get("hs_lastmodifieddate"),
            "created_at": created_at,
            "updated_at": updated_at,
            "archived": product.get("archived"),
            "url": _product_url(product, product_id=product_id),
            "properties": props,
            "raw": product,
        },
    )


def _content(*, name: str, price: float | int | None, sku: str, product_type: str) -> str:
    parts = [f"HubSpot product {name}"]
    if price is not None:
        parts.append(f"price {price:g}")
    if sku:
        parts.append(f"sku {sku}")
    if product_type:
        parts.append(f"type {product_type}")
    return "; ".join(parts)


def _created_after(product: dict[str, Any], created_after: datetime | None) -> bool:
    if created_after is None:
        return True
    props = product.get("properties") if isinstance(product.get("properties"), dict) else {}
    created_at = _parse_dt(props.get("createdate") or product.get("createdAt"))
    return created_at is not None and created_at > created_after


def _product_url(product: dict[str, Any], *, product_id: str) -> str:
    url = _text(product.get("url") or product.get("web_url"))
    if url:
        return url
    return f"https://app.hubspot.com/contacts/product/{product_id}" if product_id else ""


def _next_after(body: dict[str, Any]) -> str | None:
    paging = body.get("paging") if isinstance(body.get("paging"), dict) else {}
    next_page = paging.get("next") if isinstance(paging.get("next"), dict) else {}
    return _optional(next_page.get("after"))


def _bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


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


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return []
    strings: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _text(item)
        if text and text not in seen:
            seen.add(text)
            strings.append(text)
    return strings


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
