"""Tests for Asana task stories import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.asana_task_stories_adapter import AsanaTaskStoriesAdapter
from max.types.signal import SignalSourceType


def _story(number: int, *, task_gid: str = "t1", subtype: str = "comment_added") -> dict:
    return {
        "gid": f"s{number}",
        "type": "comment",
        "resource_subtype": subtype,
        "text": f"Please update the launch note {number}.",
        "html_text": f"<body>Please update the launch note {number}.</body>",
        "created_by": {"gid": "u1", "name": "Ada Lovelace", "email": "ada@example.com"},
        "created_at": "2026-05-03T09:00:00Z",
        "permalink_url": f"https://app.asana.com/0/{task_gid}/{number}/f",
        "target": {"gid": task_gid, "name": "Launch task"},
    }


@pytest.mark.asyncio
async def test_asana_task_stories_fetches_pages_and_maps_comment_stories() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"data": [_story(1)], "next_page": {"offset": "next-offset"}},
            )
        return httpx.Response(200, json={"data": [_story(2)], "next_page": None})

    adapter = AsanaTaskStoriesAdapter(
        access_token="asana-token",
        api_url="https://asana.example/api/1.0",
        config={
            "task_gids": ["t1"],
            "workspace_gid": "w1",
            "page_size": 1,
            "include_html_text": True,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/1.0/tasks/t1/stories"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["workspace"] == "w1"
    assert "html_text" in requests[0].url.params["opt_fields"]
    assert "created_by.name" in requests[0].url.params["opt_fields"]
    assert requests[1].url.params["offset"] == "next-offset"
    assert requests[0].headers["Authorization"] == "Bearer asana-token"
    assert [signal.metadata["asana_story_gid"] for signal in signals] == ["s1", "s2"]
    signal = signals[0]
    assert signal.id == "asana-task-story:t1:s1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "asana_task_stories_import"
    assert signal.title == "Asana task t1 comment added"
    assert signal.content == "Please update the launch note 1."
    assert signal.url == "https://app.asana.com/0/t1/1/f"
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["asana_task_gid"] == "t1"
    assert signal.metadata["story_type"] == "comment"
    assert signal.metadata["resource_subtype"] == "comment_added"
    assert signal.metadata["html_text"] == "<body>Please update the launch note 1.</body>"
    assert signal.metadata["author"]["gid"] == "u1"
    assert signal.metadata["author"]["email"] == "ada@example.com"
    assert signal.metadata["created_at"] == "2026-05-03T09:00:00Z"
    assert signal.metadata["permalink_url"] == "https://app.asana.com/0/t1/1/f"
    assert signal.metadata["target"]["gid"] == "t1"
    assert signal.metadata["raw"]["gid"] == "s1"
    assert "asana" in signal.tags
    assert "task-story" in signal.tags


@pytest.mark.asyncio
async def test_asana_task_stories_respects_limits_across_tasks_and_filters_non_comments() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        task_gid = request.url.path.split("/tasks/", 1)[1].split("/", 1)[0]
        return httpx.Response(
            200,
            json={
                "data": [
                    _story(len(requests), task_gid=task_gid),
                    _story(99, task_gid=task_gid, subtype="assigned"),
                ]
            },
        )

    adapter = AsanaTaskStoriesAdapter(
        token="asana-token",
        config={"tasks": [{"gid": "t1"}, {"gid": "t2"}], "per_task_limit": 1, "page_size": 10},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.params["limit"] == "1"
    assert [signal.metadata["asana_task_gid"] for signal in signals] == ["t1", "t2"]


@pytest.mark.asyncio
async def test_asana_task_stories_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)

    assert await AsanaTaskStoriesAdapter(config={"task_gids": ["t1"]}).fetch() == []
    assert await AsanaTaskStoriesAdapter(access_token="token").fetch() == []
    assert await AsanaTaskStoriesAdapter(access_token="token", config={"task_gids": ["t1"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_asana_task_stories_failure_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/tasks/t1/stories"):
            return httpx.Response(200, json={"data": [_story(1, task_gid="t1")]})
        return httpx.Response(500)

    adapter = AsanaTaskStoriesAdapter(
        access_token="asana-token",
        config={"task_gids": ["t1", "t2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert [signal.metadata["asana_story_gid"] for signal in signals] == ["s1"]
