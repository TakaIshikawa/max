"""Tests for HubSpot calls import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.hubspot_calls_adapter import HubSpotCallAdapter, HubSpotCallsAdapter


def _call(
    call_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
    archived: bool = False,
    updated_at: str = "2026-05-02T10:00:00Z",
) -> dict:
    return {
        "id": call_id,
        "archived": archived,
        "createdAt": "2026-05-01T10:00:00Z",
        "updatedAt": updated_at,
        "properties": {
            "hs_call_title": title or f"Call {call_id}",
            "hs_call_body": f"Call body {call_id}" if body is None else body,
            "hs_timestamp": "2026-05-01T10:00:00Z",
            "hubspot_owner_id": "owner-1",
            "hs_call_direction": "OUTBOUND",
            "hs_call_status": "COMPLETED",
            "hs_call_duration": "120000",
            "createdate": "2026-05-01T10:00:00Z",
            "hs_lastmodifieddate": updated_at,
        },
        "associations": {
            "contacts": {
                "results": [{"id": "contact-1", "type": "call_to_contact"}],
            }
        },
        "url": f"https://hubspot.example/calls/{call_id}",
    }


@pytest.mark.asyncio
async def test_hubspot_calls_fetches_pages_and_maps_call_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "results": [_call("call-1", title="Discovery call", body="Buyer asked about launch dates.")],
                    "paging": {"next": {"after": "cursor-2"}},
                },
            )
        return httpx.Response(200, json={"results": [_call("call-2", archived=True)]})

    adapter = HubSpotCallsAdapter(
        token="hubspot-token",
        api_url="https://hubspot.example",
        config={
            "page_size": 1,
            "archived": "false",
            "associations": ["contacts", "deals"],
            "properties": ["hs_call_title", "hs_call_body", "hs_timestamp"],
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert HubSpotCallAdapter is HubSpotCallsAdapter
    assert len(requests) == 2
    assert requests[0].url.path == "/crm/v3/objects/calls"
    assert requests[0].headers["Authorization"] == "Bearer hubspot-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["archived"] == "false"
    assert set(requests[0].url.params.get_list("properties")) == {
        "hs_call_title",
        "hs_call_body",
        "hs_timestamp",
    }
    assert set(requests[0].url.params.get_list("associations")) == {"contacts", "deals"}
    assert requests[1].url.params["after"] == "cursor-2"

    assert [signal.metadata["call_id"] for signal in signals] == ["call-1", "call-2"]
    signal = signals[0]
    assert signal.id == "hubspot-call:call-1"
    assert signal.source_adapter == "hubspot_calls_import"
    assert signal.source_type.value == "market"
    assert signal.title == "Discovery call"
    assert signal.content == "Buyer asked about launch dates."
    assert signal.url == "https://hubspot.example/calls/call-1"
    assert signal.author == "owner-1"
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["owner_id"] == "owner-1"
    assert signal.metadata["direction"] == "OUTBOUND"
    assert signal.metadata["status"] == "COMPLETED"
    assert signal.metadata["duration"] == 120000
    assert signal.metadata["associations"]["contacts"]["results"][0]["id"] == "contact-1"
    assert signal.metadata["raw"]["id"] == "call-1"
    assert "hubspot" in signal.tags
    assert "call" in signal.tags


@pytest.mark.asyncio
async def test_hubspot_calls_supports_after_limit_and_updated_after_alias() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    _call("old", updated_at="2026-04-01T10:00:00Z"),
                    _call("new", body="", updated_at="2026-05-03T10:00:00Z"),
                ]
            },
        )

    adapter = HubSpotCallsAdapter(
        token="hubspot-token",
        config={"after": "start", "limit": 50, "updated_after": "2026-05-01T00:00:00Z"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].url.params["after"] == "start"
    assert requests[0].url.params["limit"] == "2"
    assert [signal.metadata["call_id"] for signal in signals] == ["new"]
    assert signals[0].content == "HubSpot call; outbound; completed; 120000 ms"


@pytest.mark.asyncio
async def test_hubspot_calls_empty_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)

    assert await HubSpotCallsAdapter().fetch() == []
    assert await HubSpotCallsAdapter(token="token").fetch(limit=0) == []
