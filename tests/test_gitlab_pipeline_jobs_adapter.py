"""Tests for GitLab pipeline jobs import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_pipeline_jobs_adapter import GitLabPipelineJobsAdapter


def _job(number: int, *, status: str = "failed", pipeline_id: int = 42) -> dict:
    return {
        "id": 1000 + number,
        "name": f"test-{number}",
        "status": status,
        "stage": "test",
        "ref": "main",
        "duration": 37.5,
        "queued_duration": 3.25,
        "created_at": "2026-05-01T10:00:00Z",
        "started_at": "2026-05-01T10:01:00Z",
        "finished_at": "2026-05-01T10:02:00Z",
        "web_url": f"https://gitlab.example/group/tool/-/jobs/{1000 + number}",
        "pipeline": {
            "id": pipeline_id,
            "iid": 9,
            "project_id": 7,
            "sha": "abc123",
            "ref": "main",
            "status": "failed",
            "web_url": "https://gitlab.example/group/tool/-/pipelines/42",
        },
        "commit": {
            "id": "abc123def456",
            "short_id": "abc123",
            "title": "Fix tests",
            "author_name": "Ada",
            "web_url": "https://gitlab.example/group/tool/-/commit/abc123",
        },
        "runner": {
            "id": 5,
            "description": "shared runner",
            "runner_type": "instance_type",
            "status": "online",
            "active": True,
        },
        "user": {"username": "maintainer"},
    }


@pytest.mark.asyncio
async def test_gitlab_pipeline_jobs_paginates_filters_and_maps_project_jobs() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_job(1, status="failed"), _job(2, status="running")])
        return httpx.Response(200, json=[_job(3, status="success")])

    adapter = GitLabPipelineJobsAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"project_id": "group/tool", "scope": ["failed", "success"], "ref": "main", "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert len(requests) == 2
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab_token"
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/group%2Ftool/jobs?")
    assert requests[0].url.params["per_page"] == "2"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["ref"] == "main"
    assert requests[0].url.params.get_list("scope") == ["failed", "success"]
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["status"] for signal in signals] == ["failed", "success"]
    assert signals[0].source_adapter == "gitlab_pipeline_jobs_import"
    assert signals[0].source_type.value == "failure_data"
    assert signals[0].title == "test-1 failed"
    assert signals[0].url == "https://gitlab.example/group/tool/-/jobs/1001"
    assert signals[0].author == "maintainer"
    assert signals[0].metadata["project_id"] == "group/tool"
    assert signals[0].metadata["stage"] == "test"
    assert signals[0].metadata["ref"] == "main"
    assert signals[0].metadata["pipeline_id"] == 42
    assert signals[0].metadata["pipeline"]["web_url"].endswith("/pipelines/42")
    assert signals[0].metadata["commit_sha"] == "abc123def456"
    assert signals[0].metadata["commit"]["short_id"] == "abc123"
    assert signals[0].metadata["duration"] == 37.5
    assert signals[0].metadata["queued_duration"] == 3.25
    assert signals[0].metadata["runner"]["description"] == "shared runner"
    assert signals[0].metadata["web_url"].endswith("/jobs/1001")
    assert "pipeline-job" in signals[0].tags


@pytest.mark.asyncio
async def test_gitlab_pipeline_jobs_uses_pipeline_specific_endpoint() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_job(1, status="manual", pipeline_id=77)])

    adapter = GitLabPipelineJobsAdapter(
        token="gitlab_token",
        api_url="https://gitlab.example/api/v4",
        config={"project_id": "7", "pipeline_id": "77", "scope": "manual"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].url.path == "/api/v4/projects/7/pipelines/77/jobs"
    assert requests[0].url.params["scope"] == "manual"
    assert signals[0].metadata["status"] == "manual"
    assert signals[0].metadata["pipeline_id"] == 77


@pytest.mark.asyncio
async def test_gitlab_pipeline_jobs_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)

    assert await GitLabPipelineJobsAdapter(config={"project_id": "1"}).fetch() == []
    assert await GitLabPipelineJobsAdapter(token="token").fetch() == []
    assert await GitLabPipelineJobsAdapter(token="token", config={"project_id": "1"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_pipeline_jobs_reads_env_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env_token")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "env/project")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.env/api/v4")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_job(1, status="canceled")])

    adapter = GitLabPipelineJobsAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "env_token"
    assert requests[0].url.raw_path.startswith(b"/api/v4/projects/env%2Fproject/jobs?")
    assert signals[0].metadata["project_id"] == "env/project"
    assert signals[0].metadata["status"] == "canceled"


@pytest.mark.asyncio
async def test_gitlab_pipeline_jobs_api_or_non_json_failure_returns_empty() -> None:
    async def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    failing = GitLabPipelineJobsAdapter(
        token="gitlab_token",
        config={"project_id": "1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)),
    )
    assert await failing.fetch(limit=2) == []

    async def non_json_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    non_json = GitLabPipelineJobsAdapter(
        token="gitlab_token",
        config={"project_id": "1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(non_json_handler)),
    )
    assert await non_json.fetch(limit=2) == []
