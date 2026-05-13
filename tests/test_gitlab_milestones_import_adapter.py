"""Tests for GitLab milestones import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_milestones_adapter import (
    GitLabMilestonesAdapter,
    GitLabMilestonesImportAdapter,
)


def _milestone(number: int, *, iid: int | None = None) -> dict:
    return {
        "id": 900 + number,
        "iid": iid or number,
        "project_id": 278964,
        "title": f"Milestone {number}",
        "description": f"Release readiness {number}",
        "state": "active",
        "due_date": "2026-06-30",
        "start_date": "2026-05-01",
        "web_url": f"https://gitlab.example/group/tool/-/milestones/{number}",
        "issue_stats": {"total": 10, "closed": number, "opened": 10 - number},
        "merge_requests_count": 3,
        "expired": False,
        "created_at": "2026-05-01T10:00:00.000Z",
        "updated_at": "2026-05-02T10:00:00.000Z",
    }


@pytest.mark.asyncio
async def test_gitlab_milestones_fetches_encoded_project_paths_and_maps_signal() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_milestone(1)])

    adapter = GitLabMilestonesImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={"projects": ["group/sub/tool"], "per_page": 5},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert GitLabMilestonesAdapter is GitLabMilestonesImportAdapter
    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert str(requests[0].url).startswith(
        "https://gitlab.example/api/v4/projects/group%2Fsub%2Ftool/milestones"
    )
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"

    signal = signals[0]
    assert signal.id == "gitlab-milestone:group/sub/tool:1"
    assert signal.source_adapter == "gitlab_milestones_import"
    assert signal.source_type.value == "roadmap"
    assert signal.title == "group/sub/tool Milestone 1"
    assert signal.content == "Release readiness 1"
    assert signal.url == "https://gitlab.example/group/tool/-/milestones/1"
    assert signal.published_at is not None
    assert signal.metadata["signal_role"] == "readiness"
    assert signal.metadata["project_id"] == 278964
    assert signal.metadata["project_path"] == "group/sub/tool"
    assert signal.metadata["milestone_id"] == 901
    assert signal.metadata["milestone_iid"] == 1
    assert signal.metadata["title"] == "Milestone 1"
    assert signal.metadata["description"] == "Release readiness 1"
    assert signal.metadata["state"] == "active"
    assert signal.metadata["due_date"] == "2026-06-30"
    assert signal.metadata["start_date"] == "2026-05-01"
    assert signal.metadata["web_url"] == "https://gitlab.example/group/tool/-/milestones/1"
    assert signal.metadata["counts"]["issue_stats"]["closed"] == 1
    assert signal.metadata["counts"]["merge_requests_count"] == 3
    assert signal.metadata["expired"] is False
    assert signal.metadata["raw"]["id"] == 901
    assert {"gitlab", "milestone", "active"} <= set(signal.tags)


@pytest.mark.asyncio
async def test_gitlab_milestones_paginates_across_projects_with_limits() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raw_path = request.url.raw_path.decode().split("?", 1)[0]
        if raw_path.endswith("/group%2Ftool/milestones") and request.url.params["page"] == "1":
            return httpx.Response(200, json=[_milestone(1)])
        if raw_path.endswith("/group%2Ftool/milestones") and request.url.params["page"] == "2":
            return httpx.Response(200, json=[_milestone(2)])
        return httpx.Response(200, json=[_milestone(3)])

    adapter = GitLabMilestonesImportAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example",
        config={"project_paths": ["group/tool", "278964"], "per_page": 1, "per_project_limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [request.url.params["page"] for request in requests] == ["1", "2", "1"]
    assert requests[2].url.path == "/api/v4/projects/278964/milestones"
    assert [signal.metadata["milestone_iid"] for signal in signals] == [1, 2, 3]


@pytest.mark.asyncio
async def test_gitlab_milestones_sends_filters_and_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_milestone(1)])

    adapter = GitLabMilestonesImportAdapter(
        config={
            "project_ids": "group/tool",
            "gitlab_url": "https://gitlab.example",
            "state": "active",
            "search": "release",
            "title": "Milestone 1",
            "updated_after": "2026-05-01T00:00:00Z",
            "updated_before": "2026-05-31T00:00:00Z",
            "include_parent_milestones": True,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    await adapter.fetch(limit=1)

    assert requests[0].headers["PRIVATE-TOKEN"] == "env-token"
    assert requests[0].url.params["state"] == "active"
    assert requests[0].url.params["search"] == "release"
    assert requests[0].url.params["title"] == "Milestone 1"
    assert requests[0].url.params["updated_after"] == "2026-05-01T00:00:00Z"
    assert requests[0].url.params["updated_before"] == "2026-05-31T00:00:00Z"
    assert requests[0].url.params["include_parent_milestones"] == "true"


@pytest.mark.asyncio
async def test_gitlab_milestones_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabMilestonesImportAdapter(config={"projects": ["group/tool"]}).fetch() == []
    assert await GitLabMilestonesImportAdapter(token="token").fetch() == []
    assert await GitLabMilestonesImportAdapter(token="token", config={"projects": ["group/tool"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_milestones_http_or_non_json_failure_returns_empty() -> None:
    failing = GitLabMilestonesImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []

    non_json = GitLabMilestonesImportAdapter(
        token="gitlab-token",
        config={"projects": ["group/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="nope"))),
    )
    assert await non_json.fetch(limit=2) == []
