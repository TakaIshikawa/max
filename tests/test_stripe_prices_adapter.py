"""Tests for Stripe prices import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_prices_adapter import StripePriceAdapter, StripePricesAdapter


@pytest.mark.asyncio
async def test_fetches_prices_with_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_price("price_1")], "has_more": False})

    adapter = StripePricesAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        active=True,
        product="prod_1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=25)

    assert StripePriceAdapter is StripePricesAdapter
    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].headers["User-Agent"] == "max-stripe-prices-import/1"
    assert requests[0].url.path == "/v1/prices"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["active"] == "true"
    assert requests[0].url.params["product"] == "prod_1"
    assert signals[0].metadata["stripe_price_id"] == "price_1"
    assert signals[0].metadata["product_id"] == "prod_1"


@pytest.mark.asyncio
async def test_paginates_using_starting_after_until_has_more_is_false() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_price("price_1")], "has_more": True})
        return httpx.Response(200, json={"data": [_price("price_2")], "has_more": False})

    adapter = StripePricesAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_price_id"] for signal in signals] == ["price_1", "price_2"]
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "100"
    assert requests[1].url.params["starting_after"] == "price_1"


@pytest.mark.asyncio
async def test_price_mapping_includes_amount_currency_recurring_lookup_key_and_product_context() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    _price(
                        "price_1",
                        product={"id": "prod_1", "name": "Pro plan", "active": True, "metadata": {"tier": "pro"}},
                        metadata={"region": "us"},
                    )
                ],
                "has_more": False,
            },
        )

    adapter = StripePricesAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.id == "stripe-price:price_1"
    assert signal.source_adapter == "stripe_prices_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Stripe price price_1 (pro_monthly)"
    assert signal.url == "https://dashboard.stripe.com/prices/price_1"
    assert signal.author == "prod_1"
    assert signal.published_at is not None
    assert signal.metadata["amount"] == 2500
    assert signal.metadata["unit_amount"] == 2500
    assert signal.metadata["unit_amount_decimal"] == "2500"
    assert signal.metadata["currency"] == "usd"
    assert signal.metadata["recurring_interval"] == "month"
    assert signal.metadata["lookup_key"] == "pro_monthly"
    assert signal.metadata["product"] == {"id": "prod_1", "name": "Pro plan", "active": True, "description": None, "metadata": {"tier": "pro"}}
    assert signal.metadata["stripe_metadata"] == {"region": "us"}
    assert signal.metadata["raw"]["id"] == "price_1"
    assert "pricing" in signal.tags


@pytest.mark.asyncio
async def test_empty_response_missing_api_key_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripePricesAdapter().fetch(limit=10) == []
    assert await StripePricesAdapter(api_key="sk_test").fetch(limit=0) == []

    empty = StripePricesAdapter(
        api_key="sk_test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))),
    )
    assert await empty.fetch(limit=10) == []

    failing = StripePricesAdapter(
        api_key="sk_test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500, text="error"))),
    )
    assert await failing.fetch(limit=10) == []


def _price(price_id: str, *, product: str | dict = "prod_1", metadata: dict | None = None) -> dict:
    return {
        "id": price_id,
        "object": "price",
        "active": True,
        "unit_amount": 2500,
        "unit_amount_decimal": "2500",
        "currency": "usd",
        "recurring": {"interval": "month", "usage_type": "licensed"},
        "lookup_key": "pro_monthly",
        "product": product,
        "created": 1710000000,
        "metadata": metadata or {},
    }
