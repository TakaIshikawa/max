"""Tests for HubSpot products import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_products_adapter import HubSpotProductsAdapter
from max.types.signal import SignalSourceType


def _product(product_id: str, *, created: str = "2026-05-02T10:00:00Z") -> dict:
    return {
        "id": product_id,
        "createdAt": created,
        "updatedAt": "2026-05-03T10:00:00Z",
        "archived": False,
        "properties": {
            "name": f"Enterprise SKU {product_id}",
            "price": "99.50",
            "hs_sku": "ENT-SKU",
            "hs_product_type": "software",
            "createdate": created,
            "hs_lastmodifieddate": "2026-05-03T10:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_products_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("after") == "next":
            return httpx.Response(200, json={"results": [_product("prod-2")]})
        return httpx.Response(
            200,
            json={
                "results": [_product("prod-1")],
                "paging": {"next": {"after": "next"}},
            },
        )

    adapter = HubSpotProductsAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "page_size": 1,
            "properties": ["name", "price", "hs_sku", "hs_product_type", "createdate"],
            "archived": False,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/crm/v3/objects/products"
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].url.params.get_list("properties") == [
        "name",
        "price",
        "hs_sku",
        "hs_product_type",
        "createdate",
    ]
    assert requests[1].url.params["after"] == "next"
    assert [signal.metadata["product_id"] for signal in signals] == ["prod-1", "prod-2"]
    signal = signals[0]
    assert signal.id == "hubspot-product:prod-1"
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.source_adapter == "hubspot_products_import"
    assert signal.title == "Enterprise SKU prod-1"
    assert signal.metadata["hubspot_product_id"] == "prod-1"
    assert signal.metadata["name"] == "Enterprise SKU prod-1"
    assert signal.metadata["price"] == 99.5
    assert signal.metadata["sku"] == "ENT-SKU"
    assert signal.metadata["hs_product_type"] == "software"
    assert signal.metadata["createdate"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["hs_lastmodifieddate"] == "2026-05-03T10:00:00Z"
    assert signal.metadata["created_at"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-03T10:00:00Z"
    assert signal.metadata["archived"] is False
    assert signal.metadata["properties"]["name"] == "Enterprise SKU prod-1"
    assert signal.metadata["raw"]["id"] == "prod-1"
    assert signal.url == "https://app.hubspot.com/contacts/product/prod-1"


@pytest.mark.asyncio
async def test_hubspot_products_filters_created_after_and_honors_initial_after() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    _product("old", created="2026-04-01T10:00:00Z"),
                    _product("new", created="2026-05-05T10:00:00Z"),
                ]
            },
        )

    adapter = HubSpotProductsAdapter(
        token="hubspot-token",
        config={"created_after": "2026-05-01T00:00:00Z", "after": "start", "limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert requests[0].url.params["after"] == "start"
    assert requests[0].url.params["limit"] == "2"
    assert [signal.metadata["product_id"] for signal in signals] == ["new"]


@pytest.mark.asyncio
async def test_hubspot_products_empty_without_auth_or_positive_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotProductsAdapter().fetch() == []
    assert await HubSpotProductsAdapter(token="token").fetch(limit=0) == []
