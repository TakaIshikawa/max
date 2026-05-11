"""Tests for Asana task import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.asana_adapter import AsanaAdapter


@pytest.mark.asyncio
async def test_asana_fetch_maps_and_deduplicates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "asana_env")
    requests: list[httpx.Request] = []
    task = {"gid": "t1", "name": "Task", "notes": "Notes", "completed": False, "assignee": {"name": "Ada"}, "tags": [{"name": "Customer"}], "due_on": "2026-05-10", "permalink_url": "https://asana.test/t1", "custom_fields": [{"name": "Stage", "display_value": "Beta"}], "created_at": "2026-05-01T00:00:00Z", "modified_at": "2026-05-02T00:00:00Z"}

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [task, task]})

    adapter = AsanaAdapter(config={"project_ids": ["p1"], "completed": False, "tags": ["Customer"]}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert requests[0].headers["Authorization"] == "Bearer asana_env"
    assert signals[0].metadata["asana_task_id"] == "t1"
    assert signals[0].metadata["custom_fields"] == {"Stage": "Beta"}


@pytest.mark.asyncio
async def test_asana_missing_token_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    assert await AsanaAdapter(config={"project_ids": ["p1"]}).fetch() == []
