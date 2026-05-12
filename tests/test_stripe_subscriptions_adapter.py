from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_subscriptions_adapter import StripeSubscriptionsAdapter


@pytest.mark.asyncio
async def test_fetches_subscriptions_with_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_subscription("sub_1")], "has_more": False})

    adapter = StripeSubscriptionsAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        status="active",
        customer="cus_1",
        price="price_1",
        created_gte=1700000000,
        created_lte=1800000000,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=25)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["status"] == "active"
    assert requests[0].url.params["customer"] == "cus_1"
    assert requests[0].url.params["price"] == "price_1"
    assert requests[0].url.params["created[gte]"] == "1700000000"
    assert requests[0].url.params["created[lte]"] == "1800000000"
    assert requests[0].url.path == "/v1/subscriptions"
    assert signals[0].metadata["stripe_subscription_id"] == "sub_1"
    assert signals[0].metadata["customer_id"] == "cus_1"


@pytest.mark.asyncio
async def test_paginates_using_starting_after_until_has_more_is_false() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_subscription("sub_1")], "has_more": True})
        return httpx.Response(200, json={"data": [_subscription("sub_2")], "has_more": False})

    adapter = StripeSubscriptionsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_subscription_id"] for signal in signals] == ["sub_1", "sub_2"]
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "100"
    assert requests[1].url.params["starting_after"] == "sub_1"


@pytest.mark.asyncio
async def test_subscription_mapping_includes_lifecycle_billing_products_and_tags() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    _subscription(
                        "sub_1",
                        status="past_due",
                        collection_method="send_invoice",
                        cancel_at_period_end=True,
                        metadata={"tier": "enterprise"},
                    )
                ],
                "has_more": False,
            },
        )

    adapter = StripeSubscriptionsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.title == "Past_Due subscription sub_1"
    assert signal.metadata["status"] == "past_due"
    assert signal.metadata["collection_method"] == "send_invoice"
    assert signal.metadata["current_period_end"] == 1714000000
    assert signal.metadata["cancel_at_period_end"] is True
    assert signal.metadata["price_ids"] == ["price_1"]
    assert signal.metadata["product_ids"] == ["prod_1"]
    assert signal.metadata["stripe_metadata"] == {"tier": "enterprise"}
    assert "subscription" in signal.tags
    assert "past_due" in signal.tags


@pytest.mark.asyncio
async def test_missing_api_key_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripeSubscriptionsAdapter().fetch(limit=10) == []
    assert await StripeSubscriptionsAdapter(api_key="sk_test").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = StripeSubscriptionsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []


def _subscription(
    subscription_id: str,
    *,
    status: str = "active",
    collection_method: str = "charge_automatically",
    cancel_at_period_end: bool = False,
    metadata: dict | None = None,
) -> dict:
    return {
        "id": subscription_id,
        "object": "subscription",
        "status": status,
        "customer": "cus_1",
        "collection_method": collection_method,
        "created": 1710000000,
        "current_period_start": 1711000000,
        "current_period_end": 1714000000,
        "cancel_at_period_end": cancel_at_period_end,
        "cancel_at": None,
        "canceled_at": None,
        "ended_at": None,
        "trial_start": None,
        "trial_end": None,
        "items": {"data": [{"id": "si_1", "price": {"id": "price_1", "product": "prod_1"}}]},
        "metadata": metadata or {},
    }
