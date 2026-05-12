"""Tests for Zendesk ticket import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.zendesk_adapter import ZendeskAdapter


@pytest.mark.asyncio
async def test_zendesk_search_fetch_maps_and_filters_tickets() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 42,
                        "subject": "Cannot export",
                        "description": "CSV export fails",
                        "url": "https://max.zendesk.com/api/v2/tickets/42.json",
                        "requester_id": 10,
                        "submitter_id": 11,
                        "assignee_id": 12,
                        "status": "open",
                        "priority": "high",
                        "tags": ["export"],
                        "custom_fields": [{"id": 123, "value": "enterprise"}],
                        "created_at": "2026-05-01T00:00:00Z",
                        "updated_at": "2026-05-02T00:00:00Z",
                        "satisfaction_rating": {"score": "good"},
                    },
                    {"id": 43, "subject": "Solved", "status": "solved"},
                ]
            },
        )

    adapter = ZendeskAdapter(base_url="https://max.zendesk.com", email="user@example.com", token="token", config={"query": "type:ticket priority:high", "statuses": ["open"]}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert requests[0].url.path == "/api/v2/search.json"
    assert requests[0].url.params["query"] == "type:ticket priority:high"
    assert len(signals) == 1
    assert signals[0].title == "Cannot export"
    assert signals[0].metadata["zendesk_ticket_id"] == 42
    assert signals[0].metadata["requester_id"] == 10
    assert signals[0].metadata["assignee_id"] == 12
    assert signals[0].metadata["status"] == "open"
    assert signals[0].metadata["priority"] == "high"
    assert signals[0].metadata["tags"] == ["export"]
    assert signals[0].metadata["custom_fields"] == {123: "enterprise"}
    assert signals[0].metadata["satisfaction_rating"] == {"score": "good"}


@pytest.mark.asyncio
async def test_zendesk_view_fetch_follows_next_page() -> None:
    paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/tickets.json"):
            return httpx.Response(200, json={"tickets": [{"id": 1, "subject": "One"}], "next_page": "https://max.zendesk.com/api/v2/views/55/tickets/page2.json"})
        return httpx.Response(200, json={"tickets": [{"id": 2, "subject": "Two"}], "next_page": None})

    adapter = ZendeskAdapter(base_url="https://max.zendesk.com", email="user@example.com", token="token", config={"view_id": "55", "page_size": 1}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=2)

    assert [signal.metadata["zendesk_ticket_id"] for signal in signals] == [1, 2]
    assert paths == ["/api/v2/views/55/tickets.json", "/api/v2/views/55/tickets/page2.json"]


@pytest.mark.asyncio
async def test_zendesk_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    adapter = ZendeskAdapter(base_url="https://max.zendesk.com", email="user@example.com", token="token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch() == []
