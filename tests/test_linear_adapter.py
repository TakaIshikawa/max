"""Tests for Linear issue import adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from max.imports.linear_adapter import LinearAdapter
from max.types.signal import SignalSourceType


def _linear_response(*nodes: dict) -> dict:
    return {"data": {"issues": {"nodes": list(nodes)}}}


def _issue(issue_id: str = "lin-1", *, title: str = "Ship import adapter") -> dict:
    return {
        "id": issue_id,
        "identifier": "MAX-1",
        "title": title,
        "description": "Import recent customer issues.",
        "url": "https://linear.app/max/issue/MAX-1/ship-import-adapter",
        "priority": 2,
        "priorityLabel": "High",
        "createdAt": "2026-05-01T12:00:00.000Z",
        "updatedAt": "2026-05-02T12:00:00.000Z",
        "state": {"name": "In Progress"},
        "assignee": {"name": "Ada", "email": "ada@example.com"},
        "team": {"key": "MAX", "name": "Max"},
        "project": {"id": "project-1", "name": "Integrations"},
        "labels": {"nodes": [{"name": "customer"}, {"name": "import"}]},
    }


def _client(payload: dict, requests: list[httpx.Request] | None = None) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_properties_and_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "lin_env")
    adapter = LinearAdapter(config={"team_keys": ["ENG"], "project_ids": ["p1"], "states": ["Todo"], "labels": ["bug"]})

    assert adapter.name == "linear_import"
    assert adapter.source_type == SignalSourceType.ROADMAP.value
    assert adapter.token == "lin_env"
    assert adapter.team_keys == ["ENG"]
    assert adapter.project_ids == ["p1"]
    assert adapter.states == ["Todo"]
    assert adapter.labels == ["bug"]


@pytest.mark.asyncio
async def test_fetch_posts_graphql_payload_and_maps_signal() -> None:
    requests: list[httpx.Request] = []
    adapter = LinearAdapter(
        config={"team_keys": ["MAX"], "project_ids": ["project-1"], "states": ["In Progress"], "labels": ["customer"]},
        token="lin_token",
        client=_client(_linear_response(_issue()), requests),
    )

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    posted = json.loads(requests[0].read())
    assert "issues" in posted["query"]
    assert posted["variables"]["first"] == 5
    assert {"team": {"key": {"in": ["MAX"]}}} in posted["variables"]["filter"]["and"]
    assert requests[0].headers["Authorization"] == "lin_token"
    signal = signals[0]
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.title == "Ship import adapter"
    assert signal.author == "Ada"
    assert signal.metadata["linear_issue_id"] == "lin-1"
    assert signal.metadata["state"] == "In Progress"
    assert signal.metadata["priority_label"] == "High"
    assert signal.metadata["team_key"] == "MAX"
    assert "customer" in signal.tags


@pytest.mark.asyncio
async def test_fetch_respects_limit_and_deduplicates() -> None:
    adapter = LinearAdapter(
        token="lin_token",
        client=_client(_linear_response(_issue("dup"), _issue("dup"), _issue("other"))),
    )

    signals = await adapter.fetch(limit=1)

    assert [signal.metadata["linear_issue_id"] for signal in signals] == ["dup"]


@pytest.mark.asyncio
async def test_missing_token_and_api_errors_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    assert await LinearAdapter().fetch(limit=10) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}]})

    adapter = LinearAdapter(token="lin_token", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await adapter.fetch(limit=10) == []
