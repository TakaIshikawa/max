"""Tests for GitLab pipeline schedules import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_pipeline_schedules_adapter import GitLabPipelineSchedulesAdapter


def _schedule(number: int, *, active: bool = True) -> dict:
    return {
        "id": 100 + number,
        "description": f"nightly-{number}",
        "ref": "main",
        "cron": "0 2 * * *",
        "cron_timezone": "UTC",
        "active": active,
        "next_run_at": "2026-05-14T02:00:00Z",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "web_url": f"https://gitlab.example/group/tool/-/pipeline_schedules/{100 + number}",
        "owner": {
            "id": 7,
            "username": "maintainer",
            "name": "Maintainer",
            "state": "active",
            "web_url": "https://gitlab.example/maintainer",
        },
    }


@pytest.mark.asyncio
async def test_gitlab_pipeline_schedules_paginates_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_schedule(1), _schedule(2, active=False)])
        return httpx.Response(200, json=[_schedule(3)])

    adapter = GitLabPipelineSchedulesAdapter(
        token="gitlab_token",
        base_url="https://gitlab.example/api/v4",
        config={"project_path": "group/tool", "scope": "active", "active": True, "ref": "main", "owner": "maintainer", "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert len(requests) == 2
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_token"
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/group%2Ftool/pipeline_schedules?")
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["scope"] == "active"
    assert requests[0].url.params["active"] == "true"
    assert requests[0].url.params["ref"] == "main"
    assert requests[0].url.params["owner"] == "maintainer"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["gitlab_pipeline_schedule_id"] for signal in signals] == [101, 102, 103]
    assert signals[0].source_adapter == "gitlab_pipeline_schedules_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].title == "nightly-1 active"
    assert signals[0].author == "maintainer"
    assert signals[0].url.endswith("/101")
    assert signals[0].metadata["project_id"] == "group/tool"
    assert signals[0].metadata["description"] == "nightly-1"
    assert signals[0].metadata["ref"] == "main"
    assert signals[0].metadata["cron"] == "0 2 * * *"
    assert signals[0].metadata["cron_timezone"] == "UTC"
    assert signals[0].metadata["active"] is True
    assert signals[0].metadata["next_run_at"] == "2026-05-14T02:00:00Z"
    assert signals[0].metadata["owner"]["username"] == "maintainer"
    assert "pipeline-schedule" in signals[0].tags


@pytest.mark.asyncio
async def test_gitlab_pipeline_schedules_reads_env_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env_token")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "env/project")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.env/api/v4")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_schedule(1)])

    adapter = GitLabPipelineSchedulesAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "env_token"
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/env%2Fproject/pipeline_schedules?")
    assert signals[0].metadata["project_id"] == "env/project"


@pytest.mark.asyncio
async def test_gitlab_pipeline_schedules_empty_without_required_config_or_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)

    assert await GitLabPipelineSchedulesAdapter(config={"project_id": "1"}).fetch() == []
    assert await GitLabPipelineSchedulesAdapter(token="token").fetch() == []
    assert await GitLabPipelineSchedulesAdapter(token="token", config={"project_id": "1"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_pipeline_schedules_api_or_non_json_failure_returns_empty() -> None:
    async def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    failing = GitLabPipelineSchedulesAdapter(
        token="gitlab_token",
        config={"project_id": "1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)),
    )
    assert await failing.fetch(limit=2) == []

    async def non_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    non_json = GitLabPipelineSchedulesAdapter(
        token="gitlab_token",
        config={"project_id": "1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(non_json_handler)),
    )
    assert await non_json.fetch(limit=2) == []
