"""Tests for Linear project updates import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.linear_project_updates_adapter import LinearProjectUpdatesAdapter


def _update(update_id: str = "update-1", *, health: str = "onTrack") -> dict:
    return {
        "id": update_id,
        "body": "Delivery remains on track after beta feedback.",
        "health": health,
        "url": f"https://linear.app/max/project/update/{update_id}",
        "createdAt": "2026-05-01T10:00:00.000Z",
        "updatedAt": "2026-05-02T10:00:00.000Z",
        "user": {"id": "user-1", "name": "Ada", "displayName": "Ada Lovelace", "email": "ada@example.com", "url": "https://linear.app/user/ada"},
        "project": {"id": "project-1", "name": "Max Integrations", "url": "https://linear.app/max/project/integrations"},
    }


def _page(nodes: list[dict], *, cursor: str | None = None, has_next: bool = False) -> dict:
    return {"data": {"project": {"updates": {"nodes": nodes, "pageInfo": {"endCursor": cursor, "hasNextPage": has_next}}}}}


@pytest.mark.asyncio
async def test_fetch_queries_graphql_project_updates_with_cursor_pagination_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=_page([_update("update-1")], cursor="cursor-1", has_next=True))
        return httpx.Response(200, json=_page([_update("update-2", health="atRisk")]))

    adapter = LinearProjectUpdatesAdapter(
        token="lin-token",
        config={"project_ids": ["project-1"], "page_size": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer lin-token"
    first = json.loads(requests[0].read())
    second = json.loads(requests[1].read())
    assert "project(id: $projectId)" in first["query"]
    assert first["variables"]["projectId"] == "project-1"
    assert first["variables"]["first"] == 1
    assert first["variables"]["after"] is None
    assert second["variables"]["after"] == "cursor-1"
    assert [signal.id for signal in signals] == ["linear-project-update:update-1", "linear-project-update:update-2"]
    assert signals[0].source_adapter == "linear_project_updates_import"
    assert signals[0].title == "Max Integrations project update onTrack"
    assert signals[0].content == "Delivery remains on track after beta feedback."
    assert signals[0].author == "Ada Lovelace"
    assert signals[0].metadata["linear_project_update_id"] == "update-1"
    assert signals[0].metadata["project_id"] == "project-1"
    assert signals[0].metadata["project_name"] == "Max Integrations"
    assert signals[0].metadata["health"] == "onTrack"
    assert signals[0].metadata["author"]["email"] == "ada@example.com"
    assert signals[0].metadata["raw"]["id"] == "update-1"


@pytest.mark.asyncio
async def test_fetch_sends_health_filter_and_respects_config_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_page([_update("update-1"), _update("update-2")]))

    adapter = LinearProjectUpdatesAdapter(
        token="lin-token",
        config={"project_id": "project-1", "health": ["onTrack", "atRisk"], "limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    body = json.loads(requests[0].read())
    assert body["variables"]["filter"] == {"or": [{"health": {"eq": "onTrack"}}, {"health": {"eq": "atRisk"}}]}
    assert body["variables"]["first"] == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_linear_project_updates_empty_without_required_config_or_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)

    assert await LinearProjectUpdatesAdapter(config={"project_ids": ["project-1"]}).fetch(limit=10) == []
    assert await LinearProjectUpdatesAdapter(token="lin-token").fetch(limit=10) == []
    assert await LinearProjectUpdatesAdapter(token="lin-token", config={"project_ids": ["project-1"]}).fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}]})

    adapter = LinearProjectUpdatesAdapter(
        token="lin-token",
        config={"project_ids": ["project-1"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert await adapter.fetch(limit=10) == []
