"""Tests for Asana project status updates import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.asana_project_status_updates_adapter import AsanaProjectStatusUpdatesAdapter
from max.types.signal import SignalSourceType


def _status(number: int) -> dict:
    return {
        "gid": f"s{number}",
        "title": f"Launch status {number}",
        "text": f"Launch remains on track {number}",
        "html_text": f"<body>Launch remains on track {number}</body>",
        "color": "green",
        "author": {"gid": "u1", "name": "Ada Lovelace"},
        "created_at": "2026-05-03T09:00:00Z",
        "modified_at": "2026-05-03T10:00:00Z",
        "permalink_url": f"https://app.asana.com/0/project/status/{number}",
    }


@pytest.mark.asyncio
async def test_asana_project_status_updates_fetches_pages_and_maps_statuses() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"data": [_status(1)], "next_page": {"offset": "next-offset"}},
            )
        return httpx.Response(200, json={"data": [_status(2)], "next_page": None})

    adapter = AsanaProjectStatusUpdatesAdapter(
        access_token="asana-token",
        api_url="https://asana.example/api/1.0",
        config={
            "project_gids": ["p1"],
            "workspace_gid": "w1",
            "page_size": 1,
            "include_html_text": True,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/1.0/projects/p1/project_statuses"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["workspace"] == "w1"
    assert "html_text" in requests[0].url.params["opt_fields"]
    assert "author.name" in requests[0].url.params["opt_fields"]
    assert "created_at" in requests[0].url.params["opt_fields"]
    assert requests[1].url.params["offset"] == "next-offset"
    assert requests[0].headers["Authorization"] == "Bearer asana-token"
    assert [signal.metadata["asana_status_gid"] for signal in signals] == ["s1", "s2"]
    signal = signals[0]
    assert signal.id == "asana-project-status:p1:s1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "asana_project_status_updates_import"
    assert signal.title == "Launch status 1"
    assert signal.content == "Launch remains on track 1"
    assert signal.url == "https://app.asana.com/0/project/status/1"
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["asana_project_gid"] == "p1"
    assert signal.metadata["title"] == "Launch status 1"
    assert signal.metadata["text"] == "Launch remains on track 1"
    assert signal.metadata["html_text"] == "<body>Launch remains on track 1</body>"
    assert signal.metadata["color"] == "green"
    assert signal.metadata["author"]["gid"] == "u1"
    assert signal.metadata["created_at"] == "2026-05-03T09:00:00Z"
    assert signal.metadata["modified_at"] == "2026-05-03T10:00:00Z"
    assert signal.metadata["permalink_url"] == "https://app.asana.com/0/project/status/1"
    assert signal.metadata["raw"]["gid"] == "s1"
    assert "project-status" in signal.tags


@pytest.mark.asyncio
async def test_asana_project_status_updates_respects_limits_across_projects() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_status(len(requests))]})

    adapter = AsanaProjectStatusUpdatesAdapter(
        token="asana-token",
        config={"project_gids": ["p1", "p2"], "per_project_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert [signal.metadata["asana_project_gid"] for signal in signals] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_asana_project_status_updates_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)

    assert await AsanaProjectStatusUpdatesAdapter(config={"project_gids": ["p1"]}).fetch() == []
    assert await AsanaProjectStatusUpdatesAdapter(access_token="token").fetch() == []
    assert await AsanaProjectStatusUpdatesAdapter(access_token="token", config={"project_gids": ["p1"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_asana_project_status_updates_failure_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/projects/p1/project_statuses"):
            return httpx.Response(200, json={"data": [_status(1)]})
        return httpx.Response(500)

    adapter = AsanaProjectStatusUpdatesAdapter(
        access_token="asana-token",
        config={"project_gids": ["p1", "p2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert [signal.metadata["asana_status_gid"] for signal in signals] == ["s1"]
