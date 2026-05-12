"""Tests for Stripe subscription items import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_subscription_items_adapter import StripeSubscriptionItemAdapter, StripeSubscriptionItemsAdapter


@pytest.mark.asyncio
async def test_fetches_subscription_items_with_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_subscription_item("si_1")], "has_more": False})

    adapter = StripeSubscriptionItemsAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        subscription="sub_1",
        price="price_1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=25)

    assert StripeSubscriptionItemAdapter is StripeSubscriptionItemsAdapter
    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].url.path == "/v1/subscription_items"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["subscription"] == "sub_1"
    assert requests[0].url.params["price"] == "price_1"
    assert signals[0].metadata["stripe_subscription_item_id"] == "si_1"
    assert signals[0].metadata["subscription_id"] == "sub_1"
    assert signals[0].metadata["price_id"] == "price_1"
    assert signals[0].metadata["product_id"] == "prod_1"


@pytest.mark.asyncio
async def test_paginates_using_starting_after_until_has_more_is_false() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_subscription_item("si_1")], "has_more": True})
        return httpx.Response(200, json={"data": [_subscription_item("si_2")], "has_more": False})

    adapter = StripeSubscriptionItemsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_subscription_item_id"] for signal in signals] == ["si_1", "si_2"]
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "100"
    assert requests[1].url.params["starting_after"] == "si_1"


@pytest.mark.asyncio
async def test_subscription_item_mapping_includes_quantity_thresholds_periods_and_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [_subscription_item("si_1", metadata={"seat_type": "admin"})], "has_more": False},
        )

    adapter = StripeSubscriptionItemsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.source_adapter == "stripe_subscription_items_import"
    assert signal.source_type.value == "market"
    assert signal.id == "stripe-subscription-item:si_1"
    assert signal.title == "Stripe subscription item si_1"
    assert signal.url == "https://dashboard.stripe.com/subscriptions/sub_1"
    assert signal.author == "sub_1"
    assert signal.metadata["subscription_item_id"] == "si_1"
    assert signal.metadata["subscription_id"] == "sub_1"
    assert signal.metadata["price_id"] == "price_1"
    assert signal.metadata["product_id"] == "prod_1"
    assert signal.metadata["quantity"] == 5
    assert signal.metadata["billing_thresholds"] == {"usage_gte": 1000}
    assert signal.metadata["created"] == 1710000000
    assert signal.metadata["current_period_start"] == 1711000000
    assert signal.metadata["current_period_end"] == 1714000000
    assert signal.metadata["stripe_metadata"] == {"seat_type": "admin"}
    assert "subscription-item" in signal.tags


@pytest.mark.asyncio
async def test_missing_optional_nested_fields_are_normalized() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "si_1",
                        "subscription": {"id": "sub_1"},
                        "price": None,
                        "quantity": None,
                        "billing_thresholds": None,
                        "created": None,
                    }
                ],
                "has_more": False,
            },
        )

    adapter = StripeSubscriptionItemsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.metadata["subscription_id"] == "sub_1"
    assert signal.metadata["price_id"] is None
    assert signal.metadata["product_id"] is None
    assert signal.metadata["quantity"] is None
    assert signal.metadata["billing_thresholds"] is None
    assert signal.metadata["current_period_start"] is None
    assert signal.metadata["current_period_end"] is None
    assert signal.metadata["stripe_metadata"] == {}


@pytest.mark.asyncio
async def test_missing_api_key_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripeSubscriptionItemsAdapter().fetch(limit=10) == []
    assert await StripeSubscriptionItemsAdapter(api_key="sk_test").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = StripeSubscriptionItemsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []


def _subscription_item(item_id: str, *, metadata: dict | None = None) -> dict:
    return {
        "id": item_id,
        "object": "subscription_item",
        "subscription": "sub_1",
        "price": {"id": "price_1", "product": "prod_1"},
        "quantity": 5,
        "billing_thresholds": {"usage_gte": 1000},
        "created": 1710000000,
        "current_period_start": 1711000000,
        "current_period_end": 1714000000,
        "metadata": metadata or {},
    }
