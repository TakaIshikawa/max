"""Tests for Stripe refunds import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_refunds_adapter import StripeRefundsAdapter


@pytest.mark.asyncio
async def test_fetches_refunds_with_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_refund("re_1")], "has_more": False})

    adapter = StripeRefundsAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        charge="ch_1",
        payment_intent="pi_1",
        config={"created_gte": 1700000000, "created_lte": 1800000000, "page_size": 25},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=50)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].url.path == "/v1/refunds"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["charge"] == "ch_1"
    assert requests[0].url.params["payment_intent"] == "pi_1"
    assert requests[0].url.params["created[gte]"] == "1700000000"
    assert requests[0].url.params["created[lte]"] == "1800000000"
    assert signals[0].metadata["stripe_refund_id"] == "re_1"
    assert signals[0].metadata["charge_id"] == "ch_1"


@pytest.mark.asyncio
async def test_paginates_using_starting_after_until_has_more_is_false() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_refund("re_1")], "has_more": True})
        return httpx.Response(200, json={"data": [_refund("re_2")], "has_more": False})

    adapter = StripeRefundsAdapter(api_key="sk_test", config={"page_size": 100}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_refund_id"] for signal in signals] == ["re_1", "re_2"]
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "100"
    assert requests[1].url.params["starting_after"] == "re_1"


@pytest.mark.asyncio
async def test_refund_mapping_includes_core_fields_and_raw_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [_refund("re_1", status="failed", reason="requested_by_customer", metadata={"plan": "enterprise"})], "has_more": False},
        )

    adapter = StripeRefundsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.source_adapter == "stripe_refunds_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Stripe refund re_1 failed"
    assert signal.url == "https://dashboard.stripe.com/payments/pi_1"
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["refund_id"] == "re_1"
    assert signal.metadata["amount"] == 12500
    assert signal.metadata["currency"] == "usd"
    assert signal.metadata["status"] == "failed"
    assert signal.metadata["charge_id"] == "ch_1"
    assert signal.metadata["payment_intent_id"] == "pi_1"
    assert signal.metadata["reason"] == "requested_by_customer"
    assert signal.metadata["receipt_number"] == "1234-5678"
    assert signal.metadata["balance_transaction"] == "txn_1"
    assert signal.metadata["failure_balance_transaction"] == "txn_failure_1"
    assert signal.metadata["failure_reason"] == "expired_or_canceled_card"
    assert signal.metadata["created"] == 1710000000
    assert signal.metadata["stripe_metadata"] == {"plan": "enterprise"}
    assert signal.metadata["raw"]["id"] == "re_1"
    assert signal.published_at is not None
    assert "refund" in signal.tags


@pytest.mark.asyncio
async def test_empty_response_missing_api_key_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripeRefundsAdapter().fetch(limit=10) == []
    assert await StripeRefundsAdapter(api_key="sk_test").fetch(limit=0) == []

    async def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [], "has_more": False})

    empty_adapter = StripeRefundsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(empty_handler)))
    assert await empty_adapter.fetch(limit=10) == []

    async def failure_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    failure_adapter = StripeRefundsAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(failure_handler)))
    assert await failure_adapter.fetch(limit=10) == []


def _refund(refund_id: str, *, status: str = "succeeded", reason: str | None = None, metadata: dict | None = None) -> dict:
    return {
        "id": refund_id,
        "object": "refund",
        "amount": 12500,
        "currency": "usd",
        "status": status,
        "charge": "ch_1",
        "payment_intent": "pi_1",
        "reason": reason,
        "receipt_number": "1234-5678",
        "created": 1710000000,
        "balance_transaction": "txn_1",
        "failure_balance_transaction": "txn_failure_1" if status == "failed" else None,
        "failure_reason": "expired_or_canceled_card" if status == "failed" else None,
        "metadata": metadata or {},
    }
