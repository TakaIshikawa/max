"""Tests for Asana project tasks import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.asana_project_tasks_adapter import AsanaProjectTasksAdapter
from max.types.signal import SignalSourceType


def _task(number: int, *, assignee: str = "Ada Lovelace", section: str = "Review") -> dict:
    return {
        "gid": f"t{number}",
        "name": f"Finalize launch checklist {number}",
        "notes": f"Confirm rollout owner {number}.",
        "completed": False,
        "completed_at": None,
        "assignee": {"gid": "u1", "name": assignee},
        "memberships": [{"section": {"gid": "s1", "name": section}}],
        "tags": [{"name": "Launch"}],
        "due_on": "2026-05-10",
        "permalink_url": f"https://app.asana.com/0/project/task/{number}",
        "custom_fields": [{"name": "Stage", "display_value": "Beta"}],
        "created_at": "2026-05-01T10:00:00Z",
        "modified_at": "2026-05-02T10:00:00Z",
    }


@pytest.mark.asyncio
async def test_asana_project_tasks_fetches_pages_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "data": [
                        _task(1),
                        _task(99, assignee="Grace Hopper"),
                        _task(100, section="Backlog"),
                    ],
                    "next_page": {"offset": "next-offset"},
                },
            )
        return httpx.Response(200, json={"data": [_task(2)], "next_page": None})

    adapter = AsanaProjectTasksAdapter(
        access_token="asana-token",
        api_url="https://asana.example/api/1.0",
        config={
            "project_gids": ["p1"],
            "completed_since": "2026-04-01T00:00:00Z",
            "modified_since": "2026-05-01T00:00:00Z",
            "sections": ["Review"],
            "assignees": ["Ada Lovelace"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/1.0/projects/p1/tasks"
    assert requests[0].url.params["limit"] == "1"
    assert requests[0].url.params["completed_since"] == "2026-04-01T00:00:00Z"
    assert requests[0].url.params["modified_since"] == "2026-05-01T00:00:00Z"
    assert "memberships.section.name" in requests[0].url.params["opt_fields"]
    assert requests[1].url.params["offset"] == "next-offset"
    assert requests[0].headers["Authorization"] == "Bearer asana-token"
    assert [signal.metadata["asana_task_gid"] for signal in signals] == ["t1", "t2"]

    signal = signals[0]
    assert signal.id == "asana-project-task:p1:t1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "asana_project_tasks_import"
    assert signal.title == "Finalize launch checklist 1"
    assert signal.content == "Confirm rollout owner 1."
    assert signal.url == "https://app.asana.com/0/project/task/1"
    assert signal.author == "Ada Lovelace"
    assert signal.published_at is not None
    assert signal.metadata["asana_project_gid"] == "p1"
    assert signal.metadata["completed"] is False
    assert signal.metadata["assignee"]["gid"] == "u1"
    assert signal.metadata["sections"] == ["Review"]
    assert signal.metadata["tags"] == ["Launch"]
    assert signal.metadata["custom_fields"] == {"Stage": "Beta"}
    assert signal.metadata["raw"]["gid"] == "t1"
    assert "task" in signal.tags


@pytest.mark.asyncio
async def test_asana_project_tasks_respects_project_limit_and_custom_opt_fields() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_task(len(requests))]})

    adapter = AsanaProjectTasksAdapter(
        token="asana-token",
        config={"project_ids": ["p1", "p2"], "opt_fields": ["gid", "name"], "page_size": 50},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert requests[0].url.params["opt_fields"] == "gid,name"
    assert requests[0].url.params["limit"] == "1"
    assert signals[0].metadata["asana_project_gid"] == "p1"


@pytest.mark.asyncio
async def test_asana_project_tasks_supports_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASANA_ACCESS_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"data": [_task(1)]})

    adapter = AsanaProjectTasksAdapter(
        config={"project_gid": "p1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert signals[0].metadata["asana_task_gid"] == "t1"


@pytest.mark.asyncio
async def test_asana_project_tasks_empty_without_config_auth_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)

    assert await AsanaProjectTasksAdapter(config={"project_gid": "p1"}).fetch() == []
    assert await AsanaProjectTasksAdapter(access_token="token").fetch() == []
    assert await AsanaProjectTasksAdapter(access_token="token", config={"project_gid": "p1"}).fetch(limit=0) == []

    failing = AsanaProjectTasksAdapter(
        access_token="bad",
        config={"project_gid": "p1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch() == []
