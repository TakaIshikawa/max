"""Tests for Stripe payment intents import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_payment_intents_adapter import StripePaymentIntentsAdapter


@pytest.mark.asyncio
async def test_fetches_payment_intents_with_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_intent("pi_1")], "has_more": False})

    adapter = StripePaymentIntentsAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        status="succeeded",
        customer="cus_1",
        config={"created_gte": 1700000000, "created_lte": 1800000000, "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=50)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].url.path == "/v1/payment_intents"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["status"] == "succeeded"
    assert requests[0].url.params["customer"] == "cus_1"
    assert requests[0].url.params["created[gte]"] == "1700000000"
    assert requests[0].url.params["created[lte]"] == "1800000000"
    assert signals[0].metadata["stripe_payment_intent_id"] == "pi_1"
    assert signals[0].metadata["customer_id"] == "cus_1"


@pytest.mark.asyncio
async def test_paginates_using_starting_after_until_has_more_is_false() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_intent("pi_1")], "has_more": True})
        return httpx.Response(200, json={"data": [_intent("pi_2")], "has_more": False})

    adapter = StripePaymentIntentsAdapter(api_key="sk_test", config={"page_size": 100}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_payment_intent_id"] for signal in signals] == ["pi_1", "pi_2"]
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "100"
    assert requests[1].url.params["starting_after"] == "pi_1"


@pytest.mark.asyncio
async def test_payment_intent_mapping_includes_amount_cancellation_and_latest_charge() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [_intent("pi_1", status="canceled", cancellation_reason="abandoned")], "has_more": False})

    adapter = StripePaymentIntentsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.source_adapter == "stripe_payment_intents_import"
    assert signal.source_type.value == "failure_data"
    assert signal.title == "Stripe payment intent pi_1 canceled"
    assert signal.metadata["signal_role"] == "failure_data"
    assert signal.metadata["amount"] == 12500
    assert signal.metadata["amount_received"] == 0
    assert signal.metadata["currency"] == "usd"
    assert signal.metadata["status"] == "canceled"
    assert signal.metadata["cancellation_reason"] == "abandoned"
    assert signal.metadata["latest_charge"]["id"] == "ch_1"
    assert signal.metadata["latest_charge"]["failure_code"] == "card_declined"
    assert signal.metadata["stripe_metadata"] == {"plan": "enterprise"}
    assert "payment-failure" in signal.tags


@pytest.mark.asyncio
async def test_missing_api_key_limit_config_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripePaymentIntentsAdapter().fetch(limit=10) == []
    assert await StripePaymentIntentsAdapter(api_key="sk_test").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = StripePaymentIntentsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []


def _intent(intent_id: str, *, status: str = "succeeded", cancellation_reason: str | None = None) -> dict:
    return {
        "id": intent_id,
        "object": "payment_intent",
        "amount": 12500,
        "amount_capturable": 0,
        "amount_received": 12500 if status == "succeeded" else 0,
        "currency": "usd",
        "status": status,
        "customer": "cus_1",
        "cancellation_reason": cancellation_reason,
        "canceled_at": 1710000300 if cancellation_reason else None,
        "latest_charge": {
            "id": "ch_1",
            "status": "failed" if cancellation_reason else "succeeded",
            "paid": not cancellation_reason,
            "failure_code": "card_declined" if cancellation_reason else None,
            "failure_message": "Declined" if cancellation_reason else None,
        },
        "description": "Enterprise checkout",
        "created": 1710000000,
        "metadata": {"plan": "enterprise"},
    }
