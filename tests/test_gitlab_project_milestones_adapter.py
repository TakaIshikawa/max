"""Tests for GitLab project milestones import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_project_milestones_adapter import (
    GitLabProjectMilestoneAdapter,
    GitLabProjectMilestonesAdapter,
)
from max.types.signal import SignalSourceType


def _milestone(number: int, *, state: str = "active") -> dict:
    return {
        "id": 100 + number,
        "iid": number,
        "project_id": 22,
        "title": f"Release {number}",
        "description": f"Milestone {number} scope",
        "state": state,
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "due_date": "2026-06-01",
        "start_date": "2026-05-01",
        "expired": False,
        "web_url": f"https://gitlab.example/acme/app/-/milestones/{number}",
        "stats": {
            "issue_stats": {"total": 8, "closed": 3},
            "merge_requests_stats": {"total": 5, "closed": 1, "merged": 2},
        },
    }


@pytest.mark.asyncio
async def test_gitlab_project_milestones_paginates_filters_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_milestone(1)], headers={"X-Next-Page": "2"})
        if len(requests) == 2:
            return httpx.Response(200, json=[_milestone(2, state="closed")])
        return httpx.Response(200, json=[])

    adapter = GitLabProjectMilestonesAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={
            "project_path": "group/app",
            "page_size": 1,
            "state": "active",
            "search": "release",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/milestones"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["state"] == "active"
    assert requests[0].url.params["search"] == "release"
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["gitlab_milestone_id"] for signal in signals] == [101, 102]

    signal = signals[0]
    assert signal.id == "gitlab-project-milestone:group/app:101"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_project_milestones_import"
    assert signal.title == "Release 1"
    assert signal.url == "https://gitlab.example/acme/app/-/milestones/1"
    assert signal.metadata["project_id"] == "group/app"
    assert signal.metadata["iid"] == 1
    assert signal.metadata["state"] == "active"
    assert signal.metadata["start_date"] == "2026-05-01"
    assert signal.metadata["due_date"] == "2026-06-01"
    assert signal.metadata["issue_stats"] == {"total": 8, "closed": 3}
    assert signal.metadata["merge_request_stats"] == {"total": 5, "closed": 1, "merged": 2}
    assert signal.metadata["web_url"] == "https://gitlab.example/acme/app/-/milestones/1"
    assert signal.metadata["raw"]["id"] == 101
    assert "project-milestone" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_project_milestones_uses_env_config_and_api_url_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    monkeypatch.setenv("GITLAB_PROJECT_PATH", "platform/roadmap")
    monkeypatch.setenv("GITLAB_API_URL", "https://gitlab.internal")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_milestone(1)])

    adapter = GitLabProjectMilestonesAdapter(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/platform%2Froadmap/milestones"
    assert requests[0].headers["PRIVATE-TOKEN"] == "env-token"
    assert str(requests[0].url).startswith("https://gitlab.internal/api/v4/")


@pytest.mark.asyncio
async def test_gitlab_project_milestones_supports_project_id_env_and_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "42")
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_milestone(1)])

    adapter = GitLabProjectMilestoneAdapter(
        api_url="https://gitlab.example/api/v4",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert isinstance(adapter, GitLabProjectMilestonesAdapter)
    assert signals[0].metadata["project_id"] == "42"


@pytest.mark.asyncio
async def test_gitlab_project_milestones_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_ID", raising=False)
    monkeypatch.delenv("GITLAB_PROJECT_PATH", raising=False)

    assert await GitLabProjectMilestonesAdapter(config={"project_id": "1"}).fetch() == []
    assert await GitLabProjectMilestonesAdapter(token="token").fetch() == []
    assert await GitLabProjectMilestonesAdapter(token="token", config={"project_id": "1"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_project_milestones_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitLabProjectMilestonesAdapter(
        token="token",
        config={"project_id": "1"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []
