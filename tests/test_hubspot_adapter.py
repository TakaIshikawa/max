"""Tests for HubSpot deal import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.hubspot_adapter import HubSpotAdapter


@pytest.mark.asyncio
async def test_hubspot_fetch_posts_search_and_maps_deal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hub_env")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": [{"id": "d1", "properties": {"dealname": "Enterprise Deal", "amount": "12000", "dealstage": "qualified", "pipeline": "p1", "hubspot_owner_id": "owner1", "createdate": "2026-05-01T00:00:00Z", "hs_lastmodifieddate": "2026-05-02T00:00:00Z"}, "associations": {"companies": {"results": [{"id": "co1"}]}}}]})

    adapter = HubSpotAdapter(config={"pipeline_ids": ["p1"], "stage_ids": ["qualified"], "owners": ["owner1"], "min_amount": 1000}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=3)

    assert len(signals) == 1
    posted = json.loads(requests[0].read())
    assert requests[0].headers["Authorization"] == "Bearer hub_env"
    assert {"propertyName": "pipeline", "operator": "IN", "values": ["p1"]} in posted["filterGroups"][0]["filters"]
    assert signals[0].metadata["amount"] == 12000.0
    assert signals[0].metadata["company_ids"] == ["co1"]


@pytest.mark.asyncio
async def test_hubspot_missing_token_and_errors_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    assert await HubSpotAdapter().fetch() == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    adapter = HubSpotAdapter(token="bad", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []
