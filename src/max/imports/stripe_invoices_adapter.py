"""Stripe invoices import adapter."""

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


class StripeInvoicesAdapter(SourceAdapter):
    """Fetch Stripe invoices as billing and revenue signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        customer: str | None = None,
        subscription: str | None = None,
        status: str | None = None,
        collection_method: str | None = None,
        starting_after: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else (_optional(self._config.get("api_key")) or os.getenv("STRIPE_API_KEY"))
        self.api_url = (api_url or _optional(self._config.get("api_url")) or DEFAULT_STRIPE_API_URL).rstrip("/")
        self.customer = customer if customer is not None else _optional(self._config.get("customer"))
        self.subscription = subscription if subscription is not None else _optional(self._config.get("subscription"))
        self.status = status if status is not None else _optional(self._config.get("status"))
        self.collection_method = collection_method if collection_method is not None else _optional(self._config.get("collection_method"))
        self.created_gte = self._config.get("created_gte", self._config.get("created_after"))
        self.created_lte = self._config.get("created_lte", self._config.get("created_before"))
        self.starting_after = starting_after if starting_after is not None else _optional(self._config.get("starting_after"))
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_invoices_import"

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
            invoices = await self._fetch_invoices(client, limit=effective_limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for invoice in invoices:
            signal = _invoice_signal(invoice, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= effective_limit:
                break
        return signals

    async def _fetch_invoices(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        invoices: list[dict[str, Any]] = []
        starting_after = self.starting_after
        while len(invoices) < limit:
            page_limit = min(MAX_STRIPE_PAGE_LIMIT, limit - len(invoices))
            try:
                response = await client.get(
                    f"{self.api_url}/v1/invoices",
                    params=self._params(page_limit, starting_after=starting_after),
                    headers=self._headers(),
                )
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe invoices fetch failed", exc_info=True)
                return []
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            invoices.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            starting_after = _text(page[-1].get("id"))
            if not starting_after:
                break
        return invoices[:limit]

    def _params(self, limit: int, *, starting_after: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        for key in ("customer", "subscription", "status", "collection_method"):
            value = getattr(self, key)
            if value:
                params[key] = value
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
            "User-Agent": "max-stripe-invoices-import/1",
        }


StripeInvoiceAdapter = StripeInvoicesAdapter


def _invoice_signal(invoice: dict[str, Any], *, adapter_name: str) -> Signal | None:
    invoice_id = _text(invoice.get("id"))
    if not invoice_id:
        return None
    number = _text(invoice.get("number"))
    status = _text(invoice.get("status"))
    customer_id = _id(invoice.get("customer"))
    subscription_id = _id(invoice.get("subscription"))
    collection_method = _text(invoice.get("collection_method"))
    metadata = invoice.get("metadata") if isinstance(invoice.get("metadata"), dict) else {}
    hosted_url = _text(invoice.get("hosted_invoice_url"))
    return Signal(
        id=f"stripe-invoice:{invoice_id}",
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=f"{status.title() or 'Stripe'} invoice {number or invoice_id}",
        content=_content(invoice_id=invoice_id, number=number, customer_id=customer_id, status=status, amount_due=invoice.get("amount_due"), currency=_text(invoice.get("currency"))),
        url=hosted_url or f"https://dashboard.stripe.com/invoices/{invoice_id}",
        author=customer_id,
        published_at=_timestamp(invoice.get("created")),
        tags=sorted({"stripe", "invoice", "revenue", status, collection_method, _text(invoice.get("billing_reason"))} - {""})[:10],
        credibility=0.72,
        metadata={
            "signal_role": "market",
            "stripe_invoice_id": invoice_id,
            "invoice_id": invoice_id,
            "number": number or None,
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "status": status or None,
            "billing_reason": invoice.get("billing_reason"),
            "collection_method": collection_method or None,
            "amount_due": invoice.get("amount_due"),
            "amount_paid": invoice.get("amount_paid"),
            "amount_remaining": invoice.get("amount_remaining"),
            "currency": invoice.get("currency"),
            "hosted_invoice_url": invoice.get("hosted_invoice_url"),
            "invoice_pdf": invoice.get("invoice_pdf"),
            "due_date": invoice.get("due_date"),
            "finalized_at": _status_time(invoice, "finalized_at"),
            "paid_at": _status_time(invoice, "paid_at"),
            "created": invoice.get("created"),
            "stripe_metadata": metadata,
        },
    )


def _content(*, invoice_id: str, number: str, customer_id: str | None, status: str, amount_due: object, currency: str) -> str:
    parts = [f"Stripe invoice {number or invoice_id}"]
    if customer_id:
        parts.append(f"customer {customer_id}")
    if status:
        parts.append(f"status {status}")
    if amount_due is not None and currency:
        parts.append(f"amount due {amount_due} {currency.upper()}")
    return "; ".join(parts)


def _status_time(invoice: dict[str, Any], key: str) -> Any:
    status_transitions = invoice.get("status_transitions")
    if isinstance(status_transitions, dict) and status_transitions.get(key) is not None:
        return status_transitions.get(key)
    return invoice.get(key)


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
