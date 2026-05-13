"""Stripe refunds import adapter."""

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


class StripeRefundsAdapter(SourceAdapter):
    """Fetch Stripe refunds as revenue adjustment signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        charge: str | None = None,
        payment_intent: str | None = None,
        starting_after: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("STRIPE_API_KEY"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or DEFAULT_STRIPE_API_URL).rstrip("/")
        self.charge = charge if charge is not None else _optional(self._config.get("charge"))
        self.payment_intent = payment_intent if payment_intent is not None else _optional(self._config.get("payment_intent"))
        self.created_gte = self._config.get("created_gte", self._config.get("created_after"))
        self.created_lte = self._config.get("created_lte", self._config.get("created_before"))
        self.starting_after = starting_after if starting_after is not None else _optional(self._config.get("starting_after"))
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_refunds_import"

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
            refunds = await self._fetch_refunds(client, limit=effective_limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for refund in refunds:
            signal = _refund_signal(refund, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= effective_limit:
                break
        return signals

    async def _fetch_refunds(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        refunds: list[dict[str, Any]] = []
        starting_after = self.starting_after
        while len(refunds) < limit:
            page_limit = min(self.page_size, limit - len(refunds))
            try:
                response = await client.get(
                    f"{self.api_url}/v1/refunds",
                    params=self._params(page_limit, starting_after=starting_after),
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe refunds fetch failed", exc_info=True)
                return []
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            refunds.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            starting_after = _text(page[-1].get("id"))
            if not starting_after:
                break
        return refunds[:limit]

    def _params(self, limit: int, *, starting_after: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        if self.charge:
            params["charge"] = self.charge
        if self.payment_intent:
            params["payment_intent"] = self.payment_intent
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
            "User-Agent": "max-stripe-refunds-import/1",
        }


StripeRefundAdapter = StripeRefundsAdapter


def _refund_signal(refund: dict[str, Any], *, adapter_name: str) -> Signal | None:
    refund_id = _text(refund.get("id"))
    if not refund_id:
        return None
    status = _text(refund.get("status"))
    currency = _text(refund.get("currency"))
    charge_id = _id(refund.get("charge"))
    payment_intent_id = _id(refund.get("payment_intent"))
    reason = _optional(refund.get("reason"))
    metadata = refund.get("metadata") if isinstance(refund.get("metadata"), dict) else {}
    return Signal(
        id=f"stripe-refund:{refund_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"Stripe refund {refund_id} {status or 'unknown'}",
        content=_content(
            refund_id=refund_id,
            amount=refund.get("amount"),
            currency=currency,
            status=status,
            charge_id=charge_id,
            payment_intent_id=payment_intent_id,
            reason=reason,
        ),
        url=_dashboard_url(refund_id=refund_id, payment_intent_id=payment_intent_id, charge_id=charge_id),
        author=charge_id or payment_intent_id,
        published_at=_timestamp(refund.get("created")),
        tags=sorted({"stripe", "refund", "revenue", status, currency, reason or ""} - {""})[:10],
        credibility=0.72,
        metadata={
            "signal_role": "market",
            "stripe_refund_id": refund_id,
            "refund_id": refund_id,
            "amount": refund.get("amount"),
            "currency": refund.get("currency"),
            "status": status or None,
            "charge_id": charge_id,
            "payment_intent_id": payment_intent_id,
            "reason": reason,
            "receipt_number": refund.get("receipt_number"),
            "created": refund.get("created"),
            "balance_transaction": _id(refund.get("balance_transaction")),
            "failure_balance_transaction": _id(refund.get("failure_balance_transaction")),
            "failure_reason": refund.get("failure_reason"),
            "stripe_metadata": metadata,
            "raw": refund,
        },
    )


def _content(
    *,
    refund_id: str,
    amount: object,
    currency: str,
    status: str,
    charge_id: str | None,
    payment_intent_id: str | None,
    reason: str | None,
) -> str:
    parts = [f"Stripe refund {refund_id}"]
    if amount is not None and currency:
        parts.append(f"amount {amount} {currency.upper()}")
    if status:
        parts.append(f"status {status}")
    if charge_id:
        parts.append(f"charge {charge_id}")
    if payment_intent_id:
        parts.append(f"payment intent {payment_intent_id}")
    if reason:
        parts.append(f"reason {reason}")
    return "; ".join(parts)


def _dashboard_url(*, refund_id: str, payment_intent_id: str | None, charge_id: str | None) -> str:
    if payment_intent_id:
        return f"https://dashboard.stripe.com/payments/{payment_intent_id}"
    if charge_id:
        return f"https://dashboard.stripe.com/payments/{charge_id}"
    return f"https://dashboard.stripe.com/refunds/{refund_id}"


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
