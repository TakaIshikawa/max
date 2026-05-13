"""Tests for GitLab merge request commits import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.gitlab_merge_request_commits_adapter import (
    GitLabMergeRequestCommitsAdapter,
)
from max.types.signal import SignalSourceType


COMMIT = {
    "id": "40f4b7cfc9e7f7c1c9f3592ad739792e3340e0c4",
    "short_id": "40f4b7cf",
    "title": "Add import adapter",
    "message": "Add import adapter\n\nImplements pagination.",
    "author_name": "Author One",
    "author_email": "author@example.com",
    "authored_date": "2026-05-01T09:00:00Z",
    "committer_name": "Committer One",
    "committer_email": "committer@example.com",
    "committed_date": "2026-05-01T10:00:00Z",
    "created_at": "2026-05-01T10:00:00Z",
    "web_url": "https://gitlab.example/group/tool/-/commit/40f4b7cf",
    "parent_ids": ["parent-sha"],
    "trailers": {"Reviewed-by": "Reviewer"},
}


@pytest.mark.asyncio
async def test_gitlab_merge_request_commits_fetches_and_maps_signal_for_path_project() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[COMMIT], headers={"X-Next-Page": ""})

    adapter = GitLabMergeRequestCommitsAdapter(
        token="gitlab-token",
        gitlab_url="https://gitlab.example",
        config={
            "project_path": "group/tool",
            "merge_request_iids": [17],
            "per_page": 5,
            "since": "2026-05-01T00:00:00Z",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].headers["PRIVATE-TOKEN"] == "gitlab-token"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["User-Agent"] == "max-gitlab-merge-request-commits-import/1"
    assert str(requests[0].url) == (
        "https://gitlab.example/api/v4/projects/group%2Ftool/merge_requests/17/commits"
        "?page=1&per_page=5&since=2026-05-01T00%3A00%3A00Z"
    )
    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "gitlab-mr-commit:group/tool:17:40f4b7cfc9e7f7c1c9f3592ad739792e3340e0c4"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "gitlab_merge_request_commits_import"
    assert signal.title == "group/tool !17 commit 40f4b7cf: Add import adapter"
    assert signal.content == COMMIT["message"]
    assert signal.url == COMMIT["web_url"]
    assert signal.author == "Author One"
    assert signal.metadata["project_id"] == "group/tool"
    assert signal.metadata["merge_request_iid"] == "17"
    assert signal.metadata["sha"] == COMMIT["id"]
    assert signal.metadata["short_id"] == "40f4b7cf"
    assert signal.metadata["parent_ids"] == ["parent-sha"]
    assert signal.metadata["trailers"] == {"Reviewed-by": "Reviewer"}
    assert signal.metadata["raw"] == COMMIT
    assert "commit" in signal.tags


@pytest.mark.asyncio
async def test_gitlab_merge_request_commits_accepts_numeric_project_id_and_paginates() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[{**COMMIT, "id": "sha-1", "short_id": "sha-1"}],
                headers={"X-Next-Page": "2"},
            )
        return httpx.Response(
            200,
            json=[{**COMMIT, "id": "sha-2", "short_id": "sha-2"}],
            headers={"X-Next-Page": ""},
        )

    adapter = GitLabMergeRequestCommitsAdapter(
        token="gitlab-token",
        api_url="https://gitlab.example/api/v4/",
        config={"project_id": 278964, "merge_request_iid": 17, "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert [request.url.params["per_page"] for request in requests] == ["1", "1"]
    assert requests[0].url.path == "/api/v4/projects/278964/merge_requests/17/commits"
    assert [signal.metadata["sha"] for signal in signals] == ["sha-1", "sha-2"]


@pytest.mark.asyncio
async def test_gitlab_merge_request_commits_honors_global_limit_across_merge_requests() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[COMMIT])

    adapter = GitLabMergeRequestCommitsAdapter(
        token="gitlab-token",
        config={"project_path": "group/tool", "merge_request_iids": [17, 18]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert len(requests) == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_gitlab_merge_request_commits_accepts_configured_merge_requests() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[COMMIT])

    adapter = GitLabMergeRequestCommitsAdapter(
        token="gitlab-token",
        config={"merge_requests": [{"project_path": "group/tool", "merge_request_iid": 17}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].metadata["project_id"] == "group/tool"
    assert signals[0].metadata["merge_request_iid"] == "17"


@pytest.mark.asyncio
async def test_gitlab_merge_request_commits_empty_without_config_or_on_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITLAB_PRIVATE_TOKEN", raising=False)
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)

    assert await GitLabMergeRequestCommitsAdapter(config={"project_id": 1, "merge_request_iids": [2]}).fetch() == []
    assert await GitLabMergeRequestCommitsAdapter(token="token", config={"project_id": 1}).fetch() == []
    assert await GitLabMergeRequestCommitsAdapter(
        token="token", config={"project_id": 1, "merge_request_iids": [2]}
    ).fetch(limit=0) == []

    failing = GitLabMergeRequestCommitsAdapter(
        token="token",
        config={"project_id": 1, "merge_request_iids": [2]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
