"""Tests for ClickUp task import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.clickup_adapter import ClickUpAdapter


@pytest.mark.asyncio
async def test_clickup_fetch_maps_tasks_and_filters_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKUP_API_TOKEN", "clickup_env")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "id": "cu1",
                        "name": "Interview follow-up",
                        "description": "Talk to beta account",
                        "text_content": "Fallback",
                        "url": "https://app.clickup.com/t/cu1",
                        "assignees": [{"id": 7, "username": "Ada", "email": "ada@example.com"}],
                        "status": {"status": "open"},
                        "priority": {"id": "1", "priority": "urgent"},
                        "due_date": "1778371200000",
                        "date_created": "1777593600000",
                        "tags": [{"name": "customer"}],
                        "custom_fields": [{"id": "cf1", "name": "Stage", "value": "Beta"}],
                    },
                    {"id": "cu2", "name": "Closed task", "status": {"status": "closed"}},
                ]
            },
        )

    adapter = ClickUpAdapter(config={"list_id": "list1", "statuses": ["open"], "page_size": 50}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "clickup_env"
    assert requests[0].url.params["page"] == "0"
    assert signals[0].title == "Interview follow-up"
    assert signals[0].content == "Talk to beta account"
    assert signals[0].url == "https://app.clickup.com/t/cu1"
    assert signals[0].metadata["clickup_task_id"] == "cu1"
    assert signals[0].metadata["status"] == "open"
    assert signals[0].metadata["priority"] == "urgent"
    assert signals[0].metadata["assignees"] == [{"id": 7, "username": "Ada", "email": "ada@example.com"}]
    assert signals[0].metadata["tags"] == ["customer"]
    assert signals[0].metadata["custom_fields"] == {"Stage": "Beta"}


@pytest.mark.asyncio
async def test_clickup_fetch_paginates_and_deduplicates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "0":
            return httpx.Response(200, json={"tasks": [{"id": "cu1", "name": "One"}, {"id": "cu1", "name": "Duplicate"}]})
        return httpx.Response(200, json={"tasks": [{"id": "cu2", "name": "Two"}]})

    adapter = ClickUpAdapter(token="token", config={"list_id": "list1", "page_size": 2}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert [signal.metadata["clickup_task_id"] for signal in signals] == ["cu1", "cu2"]
    assert [request.url.params["page"] for request in requests] == ["0", "1"]


@pytest.mark.asyncio
async def test_clickup_fetch_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    adapter = ClickUpAdapter(token="token", config={"list_id": "list1"}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    assert await adapter.fetch() == []


@pytest.mark.asyncio
async def test_clickup_missing_token_or_list_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLICKUP_API_TOKEN", raising=False)
    assert await ClickUpAdapter(config={"list_id": "list1"}).fetch() == []
    assert await ClickUpAdapter(token="token").fetch() == []
