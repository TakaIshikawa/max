"""Tests for GitLab pipeline bridges import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_pipeline_bridges_adapter import GitLabPipelineBridgesAdapter
from max.types.signal import SignalSourceType


def _bridge(number: int, *, status: str = "success") -> dict:
    return {
        "id": number,
        "name": "deploy downstream",
        "status": status,
        "stage": "deploy",
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-01T10:05:00Z",
        "started_at": "2026-05-01T10:01:00Z",
        "finished_at": "2026-05-01T10:04:00Z",
        "duration": 180.5,
        "queued_duration": 2.0,
        "web_url": f"https://gitlab.example/acme/app/-/jobs/{number}",
        "user": {"id": 7, "username": "ada", "name": "Ada Lovelace", "web_url": "https://gitlab.example/ada"},
        "downstream_pipeline": {
            "id": 100 + number,
            "iid": number,
            "project_id": 22,
            "sha": "abc123",
            "ref": "main",
            "status": "running",
            "web_url": f"https://gitlab.example/downstream/{number}",
        },
    }


@pytest.mark.asyncio
async def test_gitlab_pipeline_bridges_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_bridge(1)], headers={"X-Next-Page": "2"})
        return httpx.Response(200, json=[_bridge(2, status="failed")])

    adapter = GitLabPipelineBridgesAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={
            "project_ids": ["group/app"],
            "pipeline_ids": [99],
            "page_size": 1,
            "status": "success",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/pipelines/99/bridges"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["status"] == "success"
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["gitlab_bridge_id"] for signal in signals] == [1, 2]
    signal = signals[0]
    assert signal.id == "gitlab-bridge:group/app:99:1"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_pipeline_bridges_import"
    assert signal.title == "deploy downstream success"
    assert signal.url == "https://gitlab.example/acme/app/-/jobs/1"
    assert signal.author == "ada"
    assert signal.metadata["project_id"] == "group/app"
    assert signal.metadata["pipeline_id"] == "99"
    assert signal.metadata["name"] == "deploy downstream"
    assert signal.metadata["status"] == "success"
    assert signal.metadata["stage"] == "deploy"
    assert signal.metadata["user"]["name"] == "Ada Lovelace"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-01T10:05:00Z"
    assert signal.metadata["finished_at"] == "2026-05-01T10:04:00Z"
    assert signal.metadata["duration"] == 180.5
    assert signal.metadata["web_url"] == "https://gitlab.example/acme/app/-/jobs/1"
    assert signal.metadata["downstream_pipeline"]["id"] == 101
    assert signal.metadata["raw"]["id"] == 1
    assert signals[1].source_type == SignalSourceType.FAILURE_DATA


@pytest.mark.asyncio
async def test_gitlab_pipeline_bridges_respects_per_pipeline_limit_and_projects() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_bridge(len(requests)), _bridge(99)])

    adapter = GitLabPipelineBridgesAdapter(
        token="gitlab-token",
        config={
            "gitlab_url": "https://gitlab.example",
            "projects": [{"id": "group/app"}, {"id": "42"}],
            "pipelines": [{"id": "10"}],
            "page_size": 10,
            "per_pipeline_limit": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/pipelines/10/bridges"
    assert requests[1].url.path == "/api/v4/projects/42/pipelines/10/bridges"
    assert requests[0].url.params["per_page"] == "1"
    assert [signal.metadata["project_id"] for signal in signals] == ["group/app", "42"]


@pytest.mark.asyncio
async def test_gitlab_pipeline_bridges_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabPipelineBridgesAdapter(config={"project_id": "1", "pipeline_id": "2"}).fetch() == []
    assert await GitLabPipelineBridgesAdapter(token="token", config={"pipeline_id": "2"}).fetch() == []
    assert await GitLabPipelineBridgesAdapter(token="token", config={"project_id": "1"}).fetch() == []
    assert await GitLabPipelineBridgesAdapter(token="token", config={"project_id": "1", "pipeline_id": "2"}).fetch(limit=0) == []
