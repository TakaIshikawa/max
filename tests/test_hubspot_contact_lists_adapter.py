"""Tests for HubSpot contact lists import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_contact_lists_adapter import HubSpotContactListsAdapter


CONTACT_LIST = {
    "listId": "611",
    "name": "Newsletter contacts",
    "objectTypeId": "0-1",
    "processingType": "DYNAMIC",
    "processingStatus": "COMPLETE",
    "size": 330,
    "createdAt": "2026-05-01T10:00:00Z",
    "updatedAt": "2026-05-02T11:00:00Z",
    "filterBranch": {"filterBranchType": "OR", "filterBranches": []},
}


@pytest.mark.asyncio
async def test_hubspot_contact_lists_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.read().decode()
        if '"after":"cursor-1"' not in body:
            return httpx.Response(
                200,
                json={
                    "lists": [CONTACT_LIST],
                    "paging": {"next": {"after": "cursor-1"}},
                },
            )
        return httpx.Response(200, json={"lists": [{**CONTACT_LIST, "listId": "612", "name": "Customers"}]})

    adapter = HubSpotContactListsAdapter(
        token="hs-token",
        api_url="https://api.hubspot.test",
        config={"page_size": 1, "archived": True, "query": "contact", "processing_types": ["DYNAMIC"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/crm/v3/lists/search"
    assert requests[0].url.params["includeFilters"] == "true"
    assert requests[0].url.params["archived"] == "true"
    assert requests[0].headers["Authorization"] == "Bearer hs-token"
    assert requests[0].headers["User-Agent"] == "max-hubspot-contact-lists-import/1"
    assert requests[0].content == b'{"objectTypeId":"0-1","limit":1,"query":"contact","processingTypes":["DYNAMIC"]}'
    assert requests[1].content == b'{"objectTypeId":"0-1","limit":1,"after":"cursor-1","query":"contact","processingTypes":["DYNAMIC"]}'

    signal = signals[0]
    assert signal.id == "hubspot-contact-list:611"
    assert signal.source_adapter == "hubspot_contact_lists_import"
    assert signal.title == "HubSpot contact list Newsletter contacts"
    assert signal.content == "HubSpot contact list; Newsletter contacts; DYNAMIC; object 0-1; size 330; archived False"
    assert signal.metadata["list_id"] == "611"
    assert signal.metadata["name"] == "Newsletter contacts"
    assert signal.metadata["processing_type"] == "DYNAMIC"
    assert signal.metadata["object_type"] == "0-1"
    assert signal.metadata["size"] == 330
    assert signal.metadata["count"] == 330
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["archived"] is False
    assert signal.metadata["filters"] == CONTACT_LIST["filterBranch"]
    assert signal.metadata["raw"] == CONTACT_LIST


@pytest.mark.asyncio
async def test_hubspot_contact_lists_respects_limit_and_filters_contact_object_type() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {**CONTACT_LIST, "listId": "611"},
                    {**CONTACT_LIST, "listId": "deal-list", "objectTypeId": "0-3"},
                ]
            },
        )

    adapter = HubSpotContactListsAdapter(
        access_token="hs-token",
        config={"limit": 100},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["archived"] == "false"
    assert requests[0].content == b'{"objectTypeId":"0-1","limit":1}'
    assert [signal.metadata["list_id"] for signal in signals] == ["611"]


@pytest.mark.asyncio
async def test_hubspot_contact_lists_empty_without_token_or_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_PRIVATE_APP_TOKEN", raising=False)

    assert await HubSpotContactListsAdapter().fetch() == []
    assert await HubSpotContactListsAdapter(token="token").fetch(limit=0) == []

    failing = HubSpotContactListsAdapter(
        token="bad",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
