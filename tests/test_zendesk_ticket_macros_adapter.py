"""Tests for Zendesk ticket macros import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.zendesk_ticket_macros_adapter import ZendeskTicketMacrosAdapter


MACRO = {
    "id": 123,
    "title": "Escalate billing issue",
    "active": True,
    "restriction": {"type": "Group", "ids": [11, 22]},
    "actions": [{"field": "priority", "value": "high"}, {"field": "status", "value": "open"}],
    "position": 4,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T11:00:00Z",
    "url": "https://acme.zendesk.com/api/v2/macros/123.json",
}


@pytest.mark.asyncio
async def test_zendesk_ticket_macros_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"macros": [MACRO], "next_page": "https://acme.zendesk.com/api/v2/macros.json?page=2"})
        return httpx.Response(200, json={"macros": [{**MACRO, "id": 124, "title": "Close duplicate", "active": False}], "next_page": None})

    adapter = ZendeskTicketMacrosAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="zd-token",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v2/macros.json"
    assert requests[0].url.params["per_page"] == "1"
    expected_auth = base64.b64encode(b"agent@example.com/token:zd-token").decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["macro_id"] for signal in signals] == [123, 124]

    signal = signals[0]
    assert signal.id == "zendesk-ticket-macro:123"
    assert signal.source_adapter == "zendesk_ticket_macros_import"
    assert signal.title == "Escalate billing issue"
    assert "restricted Group 11, 22" in signal.content
    assert "actions priority: high; status: open" in signal.content
    assert signal.metadata["active"] is True
    assert signal.metadata["restriction"] == {"type": "Group", "ids": [11, 22]}
    assert signal.metadata["action_summaries"] == ["priority: high", "status: open"]
    assert signal.metadata["position"] == 4
    assert signal.metadata["updated_at"] == "2026-05-02T11:00:00Z"
    assert signal.metadata["raw"] == MACRO


@pytest.mark.asyncio
async def test_zendesk_ticket_macros_supports_cursor_pagination() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"macros": [MACRO], "meta": {"has_more": True, "after_cursor": "abc"}})
        return httpx.Response(200, json={"macros": [{**MACRO, "id": 125}], "meta": {"has_more": False}})

    adapter = ZendeskTicketMacrosAdapter(
        config={"subdomain": "acme", "email": "agent@example.com", "api_token": "zd-token", "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert requests[0].url.host == "acme.zendesk.com"
    assert requests[1].url.params["page[after]"] == "abc"
    assert [signal.metadata["macro_id"] for signal in signals] == [123, 125]


@pytest.mark.asyncio
async def test_zendesk_ticket_macros_empty_and_inactive_macro() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"macros": [{**MACRO, "id": 126, "active": False, "restriction": None, "actions": []}]})

    adapter = ZendeskTicketMacrosAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="zd-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)
    assert signals[0].metadata["active"] is False
    assert signals[0].metadata["restriction"] is None
    assert "inactive" in signals[0].tags

    empty = ZendeskTicketMacrosAdapter(
        base_url="https://acme.zendesk.com",
        email="agent@example.com",
        token="zd-token",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"macros": []}))),
    )
    assert await empty.fetch(limit=5) == []
