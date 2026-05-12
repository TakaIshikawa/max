"""Stripe subscriptions import adapter."""

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


class StripeSubscriptionsAdapter(SourceAdapter):
    """Fetch Stripe subscriptions as lifecycle and billing signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        status: str | None = None,
        customer: str | None = None,
        price: str | None = None,
        created_gte: int | datetime | str | None = None,
        created_lte: int | datetime | str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("STRIPE_API_KEY"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or DEFAULT_STRIPE_API_URL).rstrip("/")
        self.status = status if status is not None else _optional(self._config.get("status"))
        self.customer = customer if customer is not None else _optional(self._config.get("customer"))
        self.price = price if price is not None else _optional(self._config.get("price"))
        self.created_gte = created_gte if created_gte is not None else self._config.get("created_gte")
        self.created_lte = created_lte if created_lte is not None else self._config.get("created_lte")
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_subscriptions_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_key:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            subscriptions = await self._fetch_subscriptions(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for subscription in subscriptions:
            signal = _subscription_signal(subscription, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_subscriptions(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        subscriptions: list[dict[str, Any]] = []
        starting_after: str | None = None
        while len(subscriptions) < limit:
            page_limit = min(MAX_STRIPE_PAGE_LIMIT, limit - len(subscriptions))
            params = self._params(page_limit, starting_after=starting_after)
            try:
                response = await client.get(f"{self.api_url}/v1/subscriptions", params=params, headers=self._headers())
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe subscriptions fetch failed", exc_info=True)
                return []

            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            subscriptions.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            last_id = _text(page[-1].get("id"))
            if not last_id:
                break
            starting_after = last_id
        return subscriptions[:limit]

    def _params(self, limit: int, *, starting_after: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        if self.status:
            params["status"] = self.status
        if self.customer:
            params["customer"] = self.customer
        if self.price:
            params["price"] = self.price
        created_gte = _created_value(self.created_gte)
        created_lte = _created_value(self.created_lte)
        if created_gte is not None:
            params["created[gte]"] = created_gte
        if created_lte is not None:
            params["created[lte]"] = created_lte
        if starting_after:
            params["starting_after"] = starting_after
        return params

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "max-stripe-subscriptions-import/1",
        }


StripeSubscriptionAdapter = StripeSubscriptionsAdapter


def _subscription_signal(subscription: dict[str, Any], *, adapter_name: str) -> Signal | None:
    subscription_id = _text(subscription.get("id"))
    if not subscription_id:
        return None
    status = _text(subscription.get("status"))
    customer_id = _customer_id(subscription.get("customer"))
    collection_method = _text(subscription.get("collection_method"))
    price_ids, product_ids = _subscription_item_ids(subscription.get("items"))
    current_period_end = _timestamp(subscription.get("current_period_end"))
    created = _timestamp(subscription.get("created"))
    cancel_at_period_end = bool(subscription.get("cancel_at_period_end")) if subscription.get("cancel_at_period_end") is not None else None
    stripe_metadata = subscription.get("metadata") if isinstance(subscription.get("metadata"), dict) else {}

    content_bits = [f"Stripe subscription {subscription_id}"]
    if customer_id:
        content_bits.append(f"customer {customer_id}")
    if status:
        content_bits.append(f"status {status}")
    if collection_method:
        content_bits.append(f"collection {collection_method}")
    if cancel_at_period_end:
        content_bits.append("cancel at period end")

    return Signal(
        id=f"stripe-subscription:{subscription_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{status.title() or 'Stripe'} subscription {subscription_id}",
        content="; ".join(content_bits),
        url=f"https://dashboard.stripe.com/subscriptions/{subscription_id}",
        author=customer_id,
        published_at=created,
        tags=sorted({"stripe", "subscription", "revenue", status, collection_method, *price_ids, *product_ids} - {""})[:10],
        credibility=0.72,
        metadata={
            "signal_role": "market",
            "stripe_subscription_id": subscription_id,
            "subscription_id": subscription_id,
            "status": status or None,
            "customer_id": customer_id,
            "collection_method": collection_method or None,
            "current_period_start": subscription.get("current_period_start"),
            "current_period_end": subscription.get("current_period_end"),
            "current_period_end_at": current_period_end.isoformat() if current_period_end else None,
            "cancel_at_period_end": cancel_at_period_end,
            "cancel_at": subscription.get("cancel_at"),
            "canceled_at": subscription.get("canceled_at"),
            "ended_at": subscription.get("ended_at"),
            "trial_start": subscription.get("trial_start"),
            "trial_end": subscription.get("trial_end"),
            "price_ids": price_ids,
            "product_ids": product_ids,
            "created": subscription.get("created"),
            "stripe_metadata": stripe_metadata,
        },
    )


def _subscription_item_ids(value: object) -> tuple[list[str], list[str]]:
    data = value.get("data") if isinstance(value, dict) and isinstance(value.get("data"), list) else []
    price_ids: list[str] = []
    product_ids: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        price_id = _text(price.get("id"))
        product_id = _text(price.get("product"))
        if price_id:
            price_ids.append(price_id)
        if product_id:
            product_ids.append(product_id)
    return price_ids[:10], product_ids[:10]


def _customer_id(value: object) -> str | None:
    if isinstance(value, dict):
        return _optional(value.get("id"))
    return _optional(value)


def _created_value(value: object) -> int | str | None:
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = _text(value)
    return text or None


def _timestamp(value: object) -> datetime | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _optional(value: object) -> str | None:
    text = _text(value)
    return text or None


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
