from __future__ import annotations

import httpx
import pytest

from max.imports.stripe_customers_adapter import StripeCustomersAdapter


@pytest.mark.asyncio
async def test_fetches_customers_with_bearer_auth_and_created_filters() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_customer("cus_1", "buyer@example.com")], "has_more": False})

    adapter = StripeCustomersAdapter(
        api_key="sk_test",
        api_url="https://stripe.example.test",
        created_after=1700000000,
        created_before=1800000000,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=25)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer sk_test"
    assert requests[0].url == "https://stripe.example.test/v1/customers?limit=25&created%5Bgte%5D=1700000000&created%5Blte%5D=1800000000"
    assert signals[0].metadata["stripe_customer_id"] == "cus_1"
    assert signals[0].metadata["email_domain"] == "example.com"


@pytest.mark.asyncio
async def test_preserves_pagination_safe_limit_behavior() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"data": [_customer("cus_1", "one@example.com")], "has_more": True})
        return httpx.Response(200, json={"data": [_customer("cus_2", "two@example.com")], "has_more": False})

    adapter = StripeCustomersAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=101)

    assert [signal.metadata["stripe_customer_id"] for signal in signals] == ["cus_1", "cus_2"]
    assert "limit=100" in str(requests[0].url)
    assert "limit=100" in str(requests[1].url)
    assert "starting_after=cus_1" in str(requests[1].url)


@pytest.mark.asyncio
async def test_customer_conversion_includes_revenue_metadata() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    _customer(
                        "cus_1",
                        "buyer@example.com",
                        balance=2500,
                        currency="usd",
                        subscriptions={"total_count": 2, "has_more": False, "data": [{"id": "sub_1"}]},
                        metadata={"plan": "pro"},
                    )
                ]
            },
        )

    adapter = StripeCustomersAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signal = (await adapter.fetch(limit=1))[0]

    assert signal.title == "buyer@example.com"
    assert signal.metadata["balance"] == 2500
    assert signal.metadata["currency"] == "usd"
    assert signal.metadata["subscriptions_hint"]["sample_ids"] == ["sub_1"]
    assert signal.metadata["stripe_metadata"] == {"plan": "pro"}
    assert "revenue" in signal.tags


@pytest.mark.asyncio
async def test_filters_by_email_domain_and_delinquent_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    _customer("cus_1", "buyer@example.com"),
                    _customer("cus_2", "buyer@other.test"),
                    _customer("cus_3", "late@example.com", delinquent=True),
                ]
            },
        )

    adapter = StripeCustomersAdapter(
        config={"email_domain": "example.com", "include_delinquent": False},
        api_key="sk_test",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=10)

    assert [signal.metadata["stripe_customer_id"] for signal in signals] == ["cus_1"]


@pytest.mark.asyncio
async def test_missing_api_key_non_positive_limit_and_failures_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    assert await StripeCustomersAdapter().fetch(limit=10) == []
    assert await StripeCustomersAdapter(api_key="sk_test").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    adapter = StripeCustomersAdapter(api_key="sk_test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []


def _customer(
    customer_id: str,
    email: str,
    *,
    balance: int = 0,
    currency: str = "usd",
    delinquent: bool = False,
    subscriptions: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    return {
        "id": customer_id,
        "object": "customer",
        "email": email,
        "balance": balance,
        "currency": currency,
        "delinquent": delinquent,
        "created": 1710000000,
        "subscriptions": subscriptions,
        "metadata": metadata or {},
    }
