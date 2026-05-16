"""Tests for HubSpot quotes import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_quotes_adapter import HubSpotQuotesAdapter
from max.types.signal import SignalSourceType


def _quote(quote_id: str) -> dict:
    return {
        "id": quote_id,
        "createdAt": "2026-05-02T10:00:00Z",
        "updatedAt": "2026-05-03T10:00:00Z",
        "archived": False,
        "associations": {"deals": {"results": [{"id": "deal-1"}]}},
        "properties": {
            "hs_title": f"Enterprise quote {quote_id}",
            "hs_quote_number": "Q-100",
            "hs_status": "APPROVED",
            "hs_quote_amount": "12500.00",
            "hs_currency": "USD",
            "hs_expiration_date": "2026-06-01",
            "hubspot_owner_id": "owner-1",
            "hs_quote_link": f"https://quotes.example/{quote_id}",
            "hs_pdf_download_link": f"https://quotes.example/{quote_id}.pdf",
            "createdate": "2026-05-02T10:00:00Z",
            "hs_lastmodifieddate": "2026-05-03T10:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_quotes_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("after") == "next":
            return httpx.Response(200, json={"results": [_quote("quote-2")]})
        return httpx.Response(
            200,
            json={
                "results": [_quote("quote-1")],
                "paging": {"next": {"after": "next"}},
            },
        )

    adapter = HubSpotQuotesAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "page_size": 1,
            "properties": ["hs_title", "hs_status", "hs_quote_amount", "hs_quote_link"],
            "archived": False,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/crm/v3/objects/quotes"
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].url.params.get_list("properties") == [
        "hs_title",
        "hs_status",
        "hs_quote_amount",
        "hs_quote_link",
    ]
    assert requests[1].url.params["after"] == "next"
    assert [signal.metadata["quote_id"] for signal in signals] == ["quote-1", "quote-2"]

    signal = signals[0]
    assert signal.id == "hubspot-quote:quote-1"
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.source_adapter == "hubspot_quotes_import"
    assert signal.title == "Enterprise quote quote-1"
    assert signal.author == "owner-1"
    assert signal.url == "https://quotes.example/quote-1"
    assert signal.metadata["hubspot_quote_id"] == "quote-1"
    assert signal.metadata["quote_number"] == "Q-100"
    assert signal.metadata["status"] == "APPROVED"
    assert signal.metadata["amount"] == 12500
    assert signal.metadata["currency"] == "USD"
    assert signal.metadata["expiration_date"] == "2026-06-01"
    assert signal.metadata["owner_id"] == "owner-1"
    assert signal.metadata["created_at"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-03T10:00:00Z"
    assert signal.metadata["pdf_url"] == "https://quotes.example/quote-1.pdf"
    assert signal.metadata["deal_association_hints"] == ["deal-1"]
    assert signal.metadata["raw"]["id"] == "quote-1"


@pytest.mark.asyncio
async def test_hubspot_quotes_honors_initial_after_and_requested_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [_quote("quote-1"), _quote("quote-2")]})

    adapter = HubSpotQuotesAdapter(
        token="hubspot-token",
        config={"after": "start", "limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["after"] == "start"
    assert requests[0].url.params["limit"] == "1"
    assert [signal.metadata["quote_id"] for signal in signals] == ["quote-1"]


@pytest.mark.asyncio
async def test_hubspot_quotes_empty_without_auth_or_positive_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotQuotesAdapter().fetch() == []
    assert await HubSpotQuotesAdapter(token="token").fetch(limit=0) == []


@pytest.mark.asyncio
async def test_hubspot_quotes_empty_on_http_error_or_malformed_response() -> None:
    failing = HubSpotQuotesAdapter(
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    malformed = HubSpotQuotesAdapter(
        token="token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))),
    )

    assert await failing.fetch(limit=5) == []
    assert await malformed.fetch(limit=5) == []
