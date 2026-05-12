"""Tests for Microsoft Planner task import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.microsoft_planner_adapter import MicrosoftPlannerAdapter


@pytest.mark.asyncio
async def test_planner_fetch_filters_completed_and_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MICROSOFT_GRAPH_TOKEN", "graph_env")
    task = {"id": "t1", "title": "Planner Task", "percentComplete": 50, "priority": 3, "dueDateTime": "2026-05-10T00:00:00Z", "startDateTime": "2026-05-01T00:00:00Z", "completedDateTime": None, "assignments": {"user1": {}}, "bucketId": "b1", "planId": "p1", "webUrl": "https://planner.test/t1", "createdDateTime": "2026-05-01T00:00:00Z", "lastModifiedDateTime": "2026-05-02T00:00:00Z"}

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [task, {**task, "id": "done", "percentComplete": 100}]})

    adapter = MicrosoftPlannerAdapter(config={"plan_ids": ["p1"], "bucket_ids": ["b1"]}, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].metadata["planner_task_id"] == "t1"
    assert signals[0].metadata["assignments"] == ["user1"]


@pytest.mark.asyncio
async def test_planner_missing_token_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MICROSOFT_GRAPH_TOKEN", raising=False)
    monkeypatch.delenv("PLANNER_ACCESS_TOKEN", raising=False)
    assert await MicrosoftPlannerAdapter(config={"plan_ids": ["p1"]}).fetch() == []
