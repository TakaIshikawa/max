"""Stripe payment intents import adapter."""

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


class StripePaymentIntentsAdapter(SourceAdapter):
    """Fetch Stripe payment intents as revenue and payment failure signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        status: str | None = None,
        customer: str | None = None,
        starting_after: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("STRIPE_API_KEY"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or DEFAULT_STRIPE_API_URL).rstrip("/")
        self.status = status if status is not None else _optional(self._config.get("status"))
        self.customer = customer if customer is not None else _optional(self._config.get("customer"))
        self.created_gte = self._config.get("created_gte", self._config.get("created_after"))
        self.created_lte = self._config.get("created_lte", self._config.get("created_before"))
        self.starting_after = starting_after if starting_after is not None else _optional(self._config.get("starting_after"))
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_payment_intents_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    @property
    def page_size(self) -> int:
        return _positive_int(self._config.get("page_size") or self._config.get("per_page"), default=30, maximum=MAX_STRIPE_PAGE_LIMIT)

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        effective_limit = min(limit, _positive_int(self._config.get("limit"), default=limit, maximum=100000))
        if effective_limit <= 0 or not self.api_key:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            intents = await self._fetch_payment_intents(client, limit=effective_limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for intent in intents:
            signal = _payment_intent_signal(intent, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= effective_limit:
                break
        return signals

    async def _fetch_payment_intents(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        intents: list[dict[str, Any]] = []
        starting_after = self.starting_after
        while len(intents) < limit:
            page_limit = min(self.page_size, limit - len(intents))
            try:
                response = await client.get(
                    f"{self.api_url}/v1/payment_intents",
                    params=self._params(page_limit, starting_after=starting_after),
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe payment intents fetch failed", exc_info=True)
                return []
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            intents.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            starting_after = _text(page[-1].get("id"))
            if not starting_after:
                break
        return intents[:limit]

    def _params(self, limit: int, *, starting_after: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        if self.status:
            params["status"] = self.status
        if self.customer:
            params["customer"] = self.customer
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
            "User-Agent": "max-stripe-payment-intents-import/1",
        }


StripePaymentIntentAdapter = StripePaymentIntentsAdapter


def _payment_intent_signal(intent: dict[str, Any], *, adapter_name: str) -> Signal | None:
    intent_id = _text(intent.get("id"))
    if not intent_id:
        return None
    status = _text(intent.get("status"))
    customer_id = _id(intent.get("customer"))
    currency = _text(intent.get("currency"))
    latest_charge = _charge_summary(intent.get("latest_charge"))
    cancellation_reason = _optional(intent.get("cancellation_reason"))
    failure = status in {"canceled", "requires_payment_method", "requires_action"} or cancellation_reason is not None
    return Signal(
        id=f"stripe-payment-intent:{intent_id}",
        source_type=SignalSourceType.FAILURE_DATA if failure else SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"Stripe payment intent {intent_id} {status or 'unknown'}",
        content=_content(intent_id=intent_id, amount=intent.get("amount"), currency=currency, status=status, customer_id=customer_id, cancellation_reason=cancellation_reason, latest_charge=latest_charge),
        url=f"https://dashboard.stripe.com/payments/{intent_id}",
        author=customer_id,
        published_at=_timestamp(intent.get("created")),
        tags=sorted({"stripe", "payment-intent", status, currency, "payment-failure" if failure else "payment"} - {""})[:10],
        credibility=0.72,
        metadata={
            "signal_role": "failure_data" if failure else "market",
            "stripe_payment_intent_id": intent_id,
            "payment_intent_id": intent_id,
            "amount": intent.get("amount"),
            "amount_capturable": intent.get("amount_capturable"),
            "amount_received": intent.get("amount_received"),
            "currency": intent.get("currency"),
            "status": status or None,
            "customer_id": customer_id,
            "cancellation_reason": cancellation_reason,
            "canceled_at": intent.get("canceled_at"),
            "latest_charge": latest_charge,
            "created": intent.get("created"),
            "description": intent.get("description"),
            "stripe_metadata": intent.get("metadata") if isinstance(intent.get("metadata"), dict) else {},
        },
    )


def _content(
    *,
    intent_id: str,
    amount: object,
    currency: str,
    status: str,
    customer_id: str | None,
    cancellation_reason: str | None,
    latest_charge: dict[str, Any],
) -> str:
    parts = [f"Stripe payment intent {intent_id}"]
    if amount is not None and currency:
        parts.append(f"amount {amount} {currency.upper()}")
    if status:
        parts.append(f"status {status}")
    if customer_id:
        parts.append(f"customer {customer_id}")
    if cancellation_reason:
        parts.append(f"canceled because {cancellation_reason}")
    if latest_charge.get("id"):
        parts.append(f"latest charge {latest_charge['id']}")
    return "; ".join(parts)


def _charge_summary(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return {
            "id": value.get("id"),
            "status": value.get("status"),
            "paid": value.get("paid"),
            "outcome": value.get("outcome"),
            "failure_code": value.get("failure_code"),
            "failure_message": value.get("failure_message"),
        }
    charge_id = _optional(value)
    return {"id": charge_id} if charge_id else {}


def _id(value: object) -> str | None:
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
