"""Tests for GitLab commit statuses import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_commit_statuses_adapter import GitLabCommitStatusesAdapter
from max.types.signal import SignalSourceType


def _status(number: int, *, status: str = "success") -> dict:
    return {
        "id": number,
        "sha": "abc123",
        "ref": "main",
        "status": status,
        "name": "ci/test",
        "stage": "test",
        "target_url": f"https://ci.example/jobs/{number}",
        "description": "unit tests",
        "allow_failure": False,
        "created_at": "2026-05-01T10:00:00Z",
        "started_at": "2026-05-01T10:01:00Z",
        "finished_at": "2026-05-01T10:04:00Z",
        "author": {"id": 7, "username": "ada", "name": "Ada Lovelace", "web_url": "https://gitlab.example/ada"},
        "commit": {"id": "abc123", "short_id": "abc123", "title": "Fix test", "author_name": "Ada"},
    }


@pytest.mark.asyncio
async def test_gitlab_commit_statuses_fetches_pages_and_maps_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_status(1)], headers={"X-Next-Page": "2"})
        return httpx.Response(200, json=[_status(2, status="failed")])

    adapter = GitLabCommitStatusesAdapter(
        private_token="gitlab-token",
        api_url="https://gitlab.example/api/v4",
        config={
            "project_ids": ["group/app"],
            "commit_shas": ["abc123"],
            "page_size": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/repository/commits/abc123/statuses"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["gitlab_status_id"] for signal in signals] == [1, 2]
    signal = signals[0]
    assert signal.id == "gitlab-commit-status:group/app:abc123:1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "gitlab_commit_statuses_import"
    assert signal.title == "ci/test success"
    assert signal.url == "https://ci.example/jobs/1"
    assert signal.author == "ada"
    assert signal.tags == ["commit", "gitlab", "main", "status", "success", "test"]
    assert signal.metadata["project_id"] == "group/app"
    assert signal.metadata["commit_sha"] == "abc123"
    assert signal.metadata["configured_commit_sha"] == "abc123"
    assert signal.metadata["ref"] == "main"
    assert signal.metadata["stage"] == "test"
    assert signal.metadata["status"] == "success"
    assert signal.metadata["name"] == "ci/test"
    assert signal.metadata["target_url"] == "https://ci.example/jobs/1"
    assert signal.metadata["author"]["name"] == "Ada Lovelace"
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["started_at"] == "2026-05-01T10:01:00Z"
    assert signal.metadata["finished_at"] == "2026-05-01T10:04:00Z"
    assert signal.metadata["raw"]["id"] == 1


@pytest.mark.asyncio
async def test_gitlab_commit_statuses_supports_explicit_commits_and_encoded_project_ids() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_status(len(requests))])

    adapter = GitLabCommitStatusesAdapter(
        token="gitlab-token",
        config={
            "gitlab_url": "https://gitlab.example",
            "commits": [
                {"project_id": "group/app", "commit_sha": "abc123"},
                {"project": "already%2Fencoded", "sha": "def456"},
                {"project_id": "group/app", "commit_sha": "abc123"},
            ],
            "page_size": 10,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/group%2Fapp/repository/commits/abc123/statuses"
    assert requests[1].url.raw_path.split(b"?", 1)[0] == b"/api/v4/projects/already%2Fencoded/repository/commits/def456/statuses"
    assert [signal.metadata["project_id"] for signal in signals] == ["group/app", "already%2Fencoded"]


@pytest.mark.asyncio
async def test_gitlab_commit_statuses_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabCommitStatusesAdapter(config={"project_id": "1", "commit_sha": "abc"}).fetch() == []
    assert await GitLabCommitStatusesAdapter(token="token", config={"commit_sha": "abc"}).fetch() == []
    assert await GitLabCommitStatusesAdapter(token="token", config={"project_id": "1"}).fetch() == []
    assert await GitLabCommitStatusesAdapter(token="token", config={"project_id": "1", "commit_sha": "abc"}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_gitlab_commit_statuses_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitLabCommitStatusesAdapter(
        token="gitlab-token",
        config={"project_id": "group/app", "commit_sha": "abc123"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=5) == []
