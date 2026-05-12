"""Stripe customers import adapter."""

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


class StripeCustomersAdapter(SourceAdapter):
    """Fetch Stripe customers as revenue and customer discovery signals."""

    def __init__(
        self,
        config: dict | None = None,
        *,
        api_key: str | None = None,
        api_url: str = DEFAULT_STRIPE_API_URL,
        created_after: int | datetime | str | None = None,
        created_before: int | datetime | str | None = None,
        email_domain: str | None = None,
        include_delinquent: bool | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config)
        self.api_key = api_key if api_key is not None else os.getenv("STRIPE_API_KEY")
        self.api_url = str(api_url).rstrip("/")
        self.created_after = created_after if created_after is not None else self._config.get("created_after")
        self.created_before = created_before if created_before is not None else self._config.get("created_before")
        self.email_domain = _domain(email_domain if email_domain is not None else self._config.get("email_domain"))
        self.include_delinquent = _bool_config(
            include_delinquent if include_delinquent is not None else self._config.get("include_delinquent"),
            default=True,
        )
        self._client = client

    @property
    def name(self) -> str:
        return "stripe_customers_import"

    @property
    def source_type(self) -> str:
        return SignalSourceType.MARKET.value

    async def fetch(self, *, limit: int = 30) -> list[Signal]:
        if limit <= 0 or not self.api_key:
            return []

        close_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            customers = await self._fetch_customers(client, limit=limit)
        finally:
            if close_client:
                await client.aclose()

        signals: list[Signal] = []
        for customer in customers:
            if not self._include_customer(customer):
                continue
            signal = _customer_signal(customer, adapter_name=self.name)
            if signal:
                signals.append(signal)
            if len(signals) >= limit:
                break
        return signals

    async def _fetch_customers(self, client: httpx.AsyncClient, *, limit: int) -> list[dict[str, Any]]:
        customers: list[dict[str, Any]] = []
        starting_after: str | None = None
        while len(customers) < limit:
            page_limit = min(MAX_STRIPE_PAGE_LIMIT, limit - len(customers))
            params = self._params(page_limit, starting_after=starting_after)
            try:
                response = await client.get(f"{self.api_url}/v1/customers", params=params, headers=self._headers())
                response.raise_for_status()
                body = response.json()
            except Exception:
                logger.warning("Stripe customers fetch failed", exc_info=True)
                return []

            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), list) else []
            page = [item for item in data if isinstance(item, dict)]
            customers.extend(page)
            if not isinstance(body, dict) or not body.get("has_more") or not page:
                break
            last_id = _text(page[-1].get("id"))
            if not last_id:
                break
            starting_after = last_id
        return customers[:limit]

    def _params(self, limit: int, *, starting_after: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": min(MAX_STRIPE_PAGE_LIMIT, max(1, limit))}
        created_after = _created_value(self.created_after)
        created_before = _created_value(self.created_before)
        if created_after is not None:
            params["created[gte]"] = created_after
        if created_before is not None:
            params["created[lte]"] = created_before
        if starting_after:
            params["starting_after"] = starting_after
        return params

    def _headers(self) -> dict[str, str]:
        assert self.api_key is not None
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "max-stripe-customers-import/1",
        }

    def _include_customer(self, customer: dict[str, Any]) -> bool:
        if self.email_domain and _email_domain(customer.get("email")) != self.email_domain:
            return False
        if not self.include_delinquent and customer.get("delinquent") is True:
            return False
        return True


StripeCustomerAdapter = StripeCustomersAdapter


def _customer_signal(customer: dict[str, Any], *, adapter_name: str) -> Signal | None:
    customer_id = _text(customer.get("id"))
    email = _text(customer.get("email"))
    if not customer_id:
        return None
    domain = _email_domain(email)
    balance = _number(customer.get("balance"))
    currency = _text(customer.get("currency")).lower() or None
    delinquent = bool(customer.get("delinquent")) if customer.get("delinquent") is not None else None
    created = _timestamp(customer.get("created"))
    subscriptions_hint = _subscriptions_hint(customer.get("subscriptions"))
    stripe_metadata = customer.get("metadata") if isinstance(customer.get("metadata"), dict) else {}

    title = email or _text(customer.get("name")) or customer_id
    content_bits = [f"Stripe customer {title}"]
    if balance is not None and currency:
        content_bits.append(f"balance {balance:g} {currency.upper()}")
    if delinquent:
        content_bits.append("delinquent")

    return Signal(
        source_type=SignalSourceType.MARKET,
        source_adapter=adapter_name,
        title=title,
        content="; ".join(content_bits),
        url=f"https://dashboard.stripe.com/customers/{customer_id}",
        author=email or None,
        published_at=created,
        tags=sorted({"stripe", "customer", "revenue", domain or "", "delinquent" if delinquent else ""} - {""})[:10],
        credibility=0.72 if not delinquent else 0.65,
        metadata={
            "signal_role": "market",
            "stripe_customer_id": customer_id,
            "customer_id": customer_id,
            "email": email or None,
            "email_domain": domain,
            "balance": balance,
            "currency": currency,
            "delinquent": delinquent,
            "created": customer.get("created"),
            "subscriptions_hint": subscriptions_hint,
            "stripe_metadata": stripe_metadata,
        },
    )


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


def _subscriptions_hint(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    data = value.get("data") if isinstance(value.get("data"), list) else []
    return {
        "total_count": value.get("total_count"),
        "has_more": value.get("has_more"),
        "sample_ids": [item.get("id") for item in data if isinstance(item, dict) and item.get("id")][:5],
    }


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


def _email_domain(value: object) -> str | None:
    text = _text(value).lower()
    if "@" not in text:
        return None
    return text.rsplit("@", 1)[-1] or None


def _domain(value: object) -> str | None:
    text = _text(value).lower()
    return text.lstrip("@") or None


def _bool_config(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
