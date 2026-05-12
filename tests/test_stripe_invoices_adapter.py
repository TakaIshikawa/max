"""Tests for Stripe invoices import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_invoices_adapter import StripeInvoicesAdapter


@pytest.mark.asyncio
async def test_fetches_invoices_with_bearer_auth_and_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_invoice("in_1")], "has_more": False})

    adapter = StripeInvoicesAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        customer="cus_1",
        subscription="sub_1",
        status="open",
        collection_method="send_invoice",
        config={"created_gte": 1700000000, "created_lte": 1800000000},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=25)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].url.path == "/v1/invoices"
    assert requests[0].url.params["limit"] == "25"
    assert requests[0].url.params["customer"] == "cus_1"
    assert requests[0].url.params["subscription"] == "sub_1"
    assert requests[0].url.params["status"] == "open"
    assert requests[0].url.params["collection_method"] == "send_invoice"
    assert requests[0].url.params["created[gte]"] == "1700000000"
    assert requests[0].url.params["created[lte]"] == "1800000000"
    assert signals[0].metadata["stripe_invoice_id"] == "in_1"
    assert signals[0].metadata["customer_id"] == "cus_1"


@pytest.mark.asyncio
async def test_paginates_using_starting_after_until_has_more_is_false() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_invoice("in_1")], "has_more": True})
        return httpx.Response(200, json={"data": [_invoice("in_2")], "has_more": False})

    adapter = StripeInvoicesAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_invoice_id"] for signal in signals] == ["in_1", "in_2"]
    assert requests[0].url.params["limit"] == "100"
    assert requests[1].url.params["limit"] == "100"
    assert requests[1].url.params["starting_after"] == "in_1"


@pytest.mark.asyncio
async def test_invoice_mapping_includes_billing_amount_urls_timestamps_and_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [_invoice("in_1", status="paid", metadata={"plan": "enterprise"})], "has_more": False},
        )

    adapter = StripeInvoicesAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.source_adapter == "stripe_invoices_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Paid invoice INV-001"
    assert signal.url == "https://pay.stripe.com/invoice/in_1"
    assert signal.metadata["number"] == "INV-001"
    assert signal.metadata["subscription_id"] == "sub_1"
    assert signal.metadata["status"] == "paid"
    assert signal.metadata["billing_reason"] == "subscription_cycle"
    assert signal.metadata["collection_method"] == "charge_automatically"
    assert signal.metadata["amount_due"] == 12500
    assert signal.metadata["amount_paid"] == 12500
    assert signal.metadata["amount_remaining"] == 0
    assert signal.metadata["currency"] == "usd"
    assert signal.metadata["hosted_invoice_url"] == "https://pay.stripe.com/invoice/in_1"
    assert signal.metadata["invoice_pdf"] == "https://pay.stripe.com/invoice/in_1.pdf"
    assert signal.metadata["due_date"] == 1712000000
    assert signal.metadata["finalized_at"] == 1710000100
    assert signal.metadata["paid_at"] == 1710000200
    assert signal.metadata["stripe_metadata"] == {"plan": "enterprise"}
    assert "invoice" in signal.tags


@pytest.mark.asyncio
async def test_missing_api_key_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripeInvoicesAdapter().fetch(limit=10) == []
    assert await StripeInvoicesAdapter(api_key="sk_test").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = StripeInvoicesAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []


def _invoice(invoice_id: str, *, status: str = "open", metadata: dict | None = None) -> dict:
    return {
        "id": invoice_id,
        "object": "invoice",
        "number": "INV-001",
        "customer": "cus_1",
        "subscription": "sub_1",
        "status": status,
        "billing_reason": "subscription_cycle",
        "collection_method": "charge_automatically",
        "amount_due": 12500,
        "amount_paid": 12500 if status == "paid" else 0,
        "amount_remaining": 0 if status == "paid" else 12500,
        "currency": "usd",
        "hosted_invoice_url": f"https://pay.stripe.com/invoice/{invoice_id}",
        "invoice_pdf": f"https://pay.stripe.com/invoice/{invoice_id}.pdf",
        "due_date": 1712000000,
        "created": 1710000000,
        "status_transitions": {"finalized_at": 1710000100, "paid_at": 1710000200 if status == "paid" else None},
        "metadata": metadata or {},
    }
