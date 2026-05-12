"""Tests for HubSpot deal line items import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_deal_line_items_adapter import HubSpotDealLineItemsAdapter
from max.types.signal import SignalSourceType


def _line_item(line_item_id: str, *, created: str = "2026-05-02T10:00:00Z") -> dict:
    return {
        "id": line_item_id,
        "createdAt": created,
        "updatedAt": "2026-05-03T10:00:00Z",
        "properties": {
            "name": f"Enterprise seat {line_item_id}",
            "quantity": "2",
            "price": "25.50",
            "amount": "51.00",
            "hs_line_item_currency_code": "USD",
            "hs_sku": "ENT-SEAT",
            "hs_product_id": "prod-1",
            "createdate": created,
            "hs_lastmodifieddate": "2026-05-03T10:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_hubspot_deal_line_items_pages_associations_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/crm/v4/objects/deals/d1/associations/line_items"):
            if request.url.params.get("after") == "next":
                return httpx.Response(
                    200,
                    json={"results": [{"toObjectId": "li-2", "associationTypes": [{"typeId": 20}]}]},
                )
            return httpx.Response(
                200,
                json={
                    "results": [{"toObjectId": "li-1", "associationTypes": [{"typeId": 20}]}],
                    "paging": {"next": {"after": "next"}},
                },
            )
        line_item_id = request.url.path.rsplit("/", 1)[1]
        return httpx.Response(200, json=_line_item(line_item_id))

    adapter = HubSpotDealLineItemsAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "deal_ids": ["d1"],
            "association_page_limit": 1,
            "properties": ["name", "quantity", "amount", "hs_sku", "createdate"],
            "association_type_ids": [20],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    association_requests = [request for request in requests if "/associations/line_items" in request.url.path]
    line_item_requests = [request for request in requests if "/crm/v3/objects/line_items/" in request.url.path]
    assert len(association_requests) == 2
    assert len(line_item_requests) == 2
    assert association_requests[0].url.params["limit"] == "1"
    assert association_requests[1].url.params["after"] == "next"
    assert association_requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert line_item_requests[0].url.params.get_list("properties") == ["name", "quantity", "amount", "hs_sku", "createdate"]
    assert [signal.metadata["line_item_id"] for signal in signals] == ["li-1", "li-2"]
    signal = signals[0]
    assert signal.id == "hubspot-deal-line-item:d1:li-1"
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.source_adapter == "hubspot_deal_line_items_import"
    assert signal.title == "Enterprise seat li-1"
    assert signal.metadata["deal_id"] == "d1"
    assert signal.metadata["hubspot_line_item_id"] == "li-1"
    assert signal.metadata["quantity"] == 2
    assert signal.metadata["price"] == 25.5
    assert signal.metadata["amount"] == 51
    assert signal.metadata["currency"] == "USD"
    assert signal.metadata["sku"] == "ENT-SEAT"
    assert signal.metadata["product_id"] == "prod-1"
    assert signal.metadata["created_at"] == "2026-05-02T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-03T10:00:00Z"
    assert signal.metadata["association_type_ids"] == ["20"]
    assert signal.metadata["association"]["toObjectId"] == "li-1"
    assert signal.metadata["raw"]["id"] == "li-1"
    assert signal.url == "https://app.hubspot.com/contacts/line-item/li-1"


@pytest.mark.asyncio
async def test_hubspot_deal_line_items_deduplicates_and_filters_created_after() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "/associations/line_items" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"toObjectId": "old", "associationTypes": [{"typeId": 20}]},
                        {"toObjectId": "new", "associationTypes": [{"typeId": 20}]},
                        {"toObjectId": "new", "associationTypes": [{"typeId": 20}]},
                    ]
                },
            )
        line_item_id = request.url.path.rsplit("/", 1)[1]
        created = "2026-04-01T10:00:00Z" if line_item_id == "old" else "2026-05-05T10:00:00Z"
        return httpx.Response(200, json=_line_item(line_item_id, created=created))

    adapter = HubSpotDealLineItemsAdapter(
        token="hubspot-token",
        config={"deal_id": "d1", "created_after": "2026-05-01T00:00:00Z", "per_deal_limit": 3},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    line_item_requests = [request for request in requests if "/crm/v3/objects/line_items/" in request.url.path]
    assert [request.url.path.rsplit("/", 1)[1] for request in line_item_requests] == ["old", "new"]
    assert [signal.metadata["line_item_id"] for signal in signals] == ["new"]


@pytest.mark.asyncio
async def test_hubspot_deal_line_items_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotDealLineItemsAdapter(config={"deal_id": "d1"}).fetch() == []
    assert await HubSpotDealLineItemsAdapter(token="token").fetch() == []
    assert await HubSpotDealLineItemsAdapter(token="token", config={"deal_id": "d1"}).fetch(limit=0) == []
