"""Tests for Freshdesk groups import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.freshdesk_groups_adapter import FreshdeskGroupsAdapter


GROUP = {
    "id": 101,
    "name": "Billing support",
    "description": "Handles billing escalations",
    "business_hour_id": 55,
    "agent_ids": [1, 2, 3],
    "auto_ticket_assign": True,
    "escalate_to": 9,
    "unassigned_for": "30m",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-02T11:00:00Z",
}


@pytest.mark.asyncio
async def test_freshdesk_groups_fetches_paginated_groups_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[GROUP], headers={"Link": '<https://acme.freshdesk.com/api/v2/groups?page=2>; rel="next"'})
        return httpx.Response(200, json=[{**GROUP, "id": 102, "name": "Enterprise"}])

    adapter = FreshdeskGroupsAdapter(
        domain="acme",
        api_key="fd-key",
        config={"page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.host == "acme.freshdesk.com"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    expected_auth = base64.b64encode(b"fd-key:X").decode()
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert [signal.metadata["group_id"] for signal in signals] == [101, 102]

    signal = signals[0]
    assert signal.id == "freshdesk-group:101"
    assert signal.source_adapter == "freshdesk_groups_import"
    assert signal.title == "Billing support"
    assert "business hours 55" in signal.content
    assert "agents 1, 2, 3" in signal.content
    assert "auto ticket assign True" in signal.content
    assert signal.url == "https://acme.freshdesk.com/a/admin/groups/101"
    assert signal.metadata["description"] == "Handles billing escalations"
    assert signal.metadata["business_hour_id"] == 55
    assert signal.metadata["agent_ids"] == [1, 2, 3]
    assert signal.metadata["escalate_to"] == 9
    assert signal.metadata["raw"] == GROUP


@pytest.mark.asyncio
async def test_freshdesk_groups_empty_and_missing_optional_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 201, "name": "General"}])

    adapter = FreshdeskGroupsAdapter(
        domain="https://acme.freshdesk.com",
        api_key="fd-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["description"] is None
    assert signals[0].metadata["agent_ids"] == []
    assert signals[0].metadata["business_hour_id"] is None

    empty = FreshdeskGroupsAdapter(
        domain="acme",
        api_key="fd-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))),
    )
    assert await empty.fetch(limit=5) == []


@pytest.mark.asyncio
async def test_freshdesk_groups_empty_without_required_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRESHDESK_DOMAIN", raising=False)
    monkeypatch.delenv("FRESHDESK_API_KEY", raising=False)

    assert await FreshdeskGroupsAdapter(api_key="fd-key").fetch() == []
    assert await FreshdeskGroupsAdapter(domain="acme").fetch() == []
    assert await FreshdeskGroupsAdapter(domain="acme", api_key="fd-key").fetch(limit=0) == []

    failing = FreshdeskGroupsAdapter(
        domain="acme",
        api_key="fd-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=5) == []
