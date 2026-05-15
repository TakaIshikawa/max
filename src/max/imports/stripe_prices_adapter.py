"""Stripe prices import adapter."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import httpx

from max.sources.base import SourceAdapter
from max.types.signal import Signal, SignalSourceType

logger = logging.getLogger(__name__)

DEFAULT_STRIPE_API_URL = "https://api.stripe.com"
MAX_STRIPE_PAGE_LIMIT = 100


class StripePricesAdapter(SourceAdapter):
    """Fetch Stripe prices as pricing catalog signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        active: bool | str | None = None,
        product: str | None = None,
        starting_after: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("STRIPE_API_KEY"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or DEFAULT_STRIPE_API_URL).rstrip("/")
        self.active = active if active is not None else self._config.get("active")
        self.product = product if product is not None else _optional(self._config.get("product"))
        self.starting_after = starting_after if starting_after is not None else _optional(self._config.get("starting_after"))
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_prices_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, _positive_int(self._config.get("limit"), default=limit, maximum=100000))
        if effective_limit <= 0 or not self.api_key:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            prices = await self._fetch_prices(client, limit=effective_limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for price in prices:
            signal = _price_signal(price, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= effective_limit:
                break
        return signals

    async def _fetch_prices(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        prices: list[dict[str, Any]] = []
        starting_after = self.starting_after
        while len(prices) < limit:
            page_limit = min(MAX_STRIPE_PAGE_LIMIT, limit - len(prices))
            try:
                response = await client.get(
                    f"{self.api_url}/v1/prices",
                    params=self._params(page_limit, starting_after=starting_after),
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe prices fetch failed", exc_info=True)
                return []
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            prices.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            starting_after = _text(page[-1].get("id"))
            if not starting_after:
                break
        return prices[:limit]

    def _params(self, limit: int, *, starting_after: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        active = _bool_param(self.active)
        if active is not None:
            params["active"] = active
        if self.product:
            params["product"] = self.product
        if starting_after:
            params["starting_after"] = starting_after
        return params

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "max-stripe-prices-import/1",
        }


StripePriceAdapter = StripePricesAdapter


def _price_signal(price: dict[str, Any], *, adapter_name: str) -> Signal | None:
    price_id = _text(price.get("id"))
    if not price_id:
        return None
    product = price.get("product")
    product_context = _product_context(product)
    product_id = product_context.get("id")
    currency = _text(price.get("currency")).lower() or None
    unit_amount = _number(price.get("unit_amount"))
    unit_amount_decimal = _optional(price.get("unit_amount_decimal"))
    recurring = price.get("recurring") if isinstance(price.get("recurring"), dict) else {}
    interval = _optional(recurring.get("interval"))
    lookup_key = _optional(price.get("lookup_key"))
    active = price.get("active") if isinstance(price.get("active"), bool) else None
    created = _timestamp(price.get("created"))

    title_bits = ["Stripe price", price_id]
    if lookup_key:
        title_bits.append(f"({lookup_key})")
    content_bits = [f"Stripe price {price_id}"]
    if unit_amount is not None and currency:
        content_bits.append(f"amount {unit_amount:g} {currency.upper()}")
    if interval:
        content_bits.append(f"recurs {interval}")
    if product_id:
        content_bits.append(f"product {product_id}")

    return Signal(
        id=f"stripe-price:{price_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=" ".join(title_bits),
        content="; ".join(content_bits),
        url=f"https://dashboard.stripe.com/prices/{price_id}",
        author=product_id,
        published_at=created,
        tags=sorted({"stripe", "price", "pricing", "catalog", currency or "", interval or "", product_id or ""} - {""})[:10],
        credibility=0.72,
        metadata={
            "signal_role": "market",
            "stripe_price_id": price_id,
            "price_id": price_id,
            "active": active,
            "amount": unit_amount,
            "unit_amount": unit_amount,
            "unit_amount_decimal": unit_amount_decimal,
            "currency": currency,
            "recurring_interval": interval,
            "recurring": recurring,
            "lookup_key": lookup_key,
            "product": product_context,
            "product_id": product_id,
            "created": price.get("created"),
            "metadata": price.get("metadata") if isinstance(price.get("metadata"), dict) else {},
            "stripe_metadata": price.get("metadata") if isinstance(price.get("metadata"), dict) else {},
            "raw": price,
        },
    )


def _product_context(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "id": _optional(value.get("id")),
            "name": value.get("name"),
            "active": value.get("active") if isinstance(value.get("active"), bool) else None,
            "description": value.get("description"),
            "metadata": value.get("metadata") if isinstance(value.get("metadata"), dict) else {},
        }
    product_id = _optional(value)
    return {"id": product_id} if product_id else {}


def _bool_param(value: object) -> str | None:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = _text(value).lower()
    if text in {"true", "1", "yes"}:
        return "true"
    if text in {"false", "0", "no"}:
        return "false"
    return None


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _number(value: object) -> float | int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    try:
        return float(str(value))
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


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
