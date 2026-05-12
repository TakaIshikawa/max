"""Stripe subscription items import adapter."""

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


class StripeSubscriptionItemsAdapter(SourceAdapter):
    """Fetch Stripe subscription items as billing and product signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        subscription: str | None = None,
        price: str | None = None,
        starting_after: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("STRIPE_API_KEY"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or DEFAULT_STRIPE_API_URL).rstrip("/")
        self.subscription = subscription if subscription is not None else _optional(self._config.get("subscription"))
        self.price = price if price is not None else _optional(self._config.get("price"))
        self.starting_after = starting_after if starting_after is not None else _optional(self._config.get("starting_after"))
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_subscription_items_import"

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
            items = await self._fetch_subscription_items(client, limit=effective_limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for item in items:
            signal = _subscription_item_signal(item, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= effective_limit:
                break
        return signals

    async def _fetch_subscription_items(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        starting_after = self.starting_after
        while len(items) < limit:
            page_limit = min(MAX_STRIPE_PAGE_LIMIT, limit - len(items))
            try:
                response = await client.get(
                    f"{self.api_url}/v1/subscription_items",
                    params=self._params(page_limit, starting_after=starting_after),
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe subscription items fetch failed", exc_info=True)
                return []
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            items.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            starting_after = _text(page[-1].get("id"))
            if not starting_after:
                break
        return items[:limit]

    def _params(self, limit: int, *, starting_after: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        if self.subscription:
            params["subscription"] = self.subscription
        if self.price:
            params["price"] = self.price
        if starting_after:
            params["starting_after"] = starting_after
        return params

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "max-stripe-subscription-items-import/1",
        }


StripeSubscriptionItemAdapter = StripeSubscriptionItemsAdapter


def _subscription_item_signal(item: dict[str, Any], *, adapter_name: str) -> Signal | None:
    item_id = _text(item.get("id"))
    if not item_id:
        return None
    subscription_id = _id(item.get("subscription"))
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    price_id = _text(price.get("id"))
    product_id = _product_id(price.get("product"))
    quantity = item.get("quantity")
    billing_thresholds = item.get("billing_thresholds") if isinstance(item.get("billing_thresholds"), dict) else None
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    created = _timestamp(item.get("created"))

    content_bits = [f"Stripe subscription item {item_id}"]
    if subscription_id:
        content_bits.append(f"subscription {subscription_id}")
    if price_id:
        content_bits.append(f"price {price_id}")
    if product_id:
        content_bits.append(f"product {product_id}")
    if quantity is not None:
        content_bits.append(f"quantity {quantity}")

    return Signal(
        id=f"stripe-subscription-item:{item_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"Stripe subscription item {item_id}",
        content="; ".join(content_bits),
        url=f"https://dashboard.stripe.com/subscriptions/{subscription_id}" if subscription_id else f"https://dashboard.stripe.com/subscription_items/{item_id}",
        author=subscription_id,
        published_at=created,
        tags=sorted({"stripe", "subscription-item", "subscription", "revenue", price_id, product_id or ""} - {""})[:10],
        credibility=0.72,
        metadata={
            "signal_role": "market",
            "stripe_subscription_item_id": item_id,
            "subscription_item_id": item_id,
            "subscription_id": subscription_id,
            "price_id": price_id or None,
            "product_id": product_id or None,
            "quantity": quantity,
            "billing_thresholds": billing_thresholds,
            "created": item.get("created"),
            "current_period_start": item.get("current_period_start"),
            "current_period_end": item.get("current_period_end"),
            "metadata": metadata,
            "stripe_metadata": metadata,
        },
    )


def _id(value: object) -> str | None:
    if isinstance(value, dict):
        return _optional(value.get("id"))
    return _optional(value)


def _product_id(value: object) -> str | None:
    if isinstance(value, dict):
        return _optional(value.get("id"))
    return _optional(value)


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value)
        except (OverflowError, OSError, ValueError):
            return None
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
