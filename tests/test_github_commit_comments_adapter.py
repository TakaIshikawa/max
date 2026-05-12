"""Tests for GitHub commit comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_commit_comments_adapter import GitHubCommitCommentsAdapter
from max.types.signal import SignalSourceType


COMMENT = {
    "url": "https://api.github.example/repos/acme/api/comments/123",
    "html_url": "https://github.example/acme/api/commit/abc123#commitcomment-123",
    "id": 123,
    "node_id": "CC_kwDOA1",
    "commit_id": "abc123def456",
    "user": {
        "login": "octocat",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "type": "User",
        "html_url": "https://github.example/octocat",
    },
    "body": "This implementation detail needs a follow-up.",
    "path": "src/app.py",
    "position": 4,
    "line": 25,
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T11:00:00Z",
}


@pytest.mark.asyncio
async def test_github_commit_comments_fetches_and_maps_comments() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[COMMENT])

    adapter = GitHubCommitCommentsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={
            "repositories": ["acme/api"],
            "page_size": 10,
            "since": "2026-05-01T00:00:00Z",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 1
    assert requests[0].url.path == "/api/v3/repos/acme/api/comments"
    assert requests[0].url.params["per_page"] == "5"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["since"] == "2026-05-01T00:00:00Z"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    signal = signals[0]
    assert signal.id == "github-commit-comment:acme/api:123"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "github_commit_comments_import"
    assert signal.title == "acme/api commit abc123d comment"
    assert signal.content == "This implementation detail needs a follow-up."
    assert signal.url == "https://github.example/acme/api/commit/abc123#commitcomment-123"
    assert signal.author == "octocat"
    assert signal.metadata["github_commit_comment_id"] == 123
    assert signal.metadata["commit_sha"] == "abc123def456"
    assert signal.metadata["path"] == "src/app.py"
    assert signal.metadata["position"] == 4
    assert signal.metadata["line"] == 25
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-01T11:00:00Z"
    assert signal.metadata["html_url"] == "https://github.example/acme/api/commit/abc123#commitcomment-123"
    assert signal.metadata["repository"] == "acme/api"
    assert signal.metadata["author"]["login"] == "octocat"
    assert "commit-comment" in signal.tags


@pytest.mark.asyncio
async def test_github_commit_comments_paginates_and_respects_limits_across_repositories() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/acme/one/comments":
            if request.url.params["page"] == "1":
                return httpx.Response(200, json=[{**COMMENT, "id": 1, "commit_id": "sha-one-a"}])
            return httpx.Response(200, json=[{**COMMENT, "id": 2, "commit_id": "sha-one-b"}])
        if request.url.path == "/repos/acme/two/comments":
            return httpx.Response(200, json=[{**COMMENT, "id": 3, "commit_id": "sha-two-a"}])
        return httpx.Response(404)

    adapter = GitHubCommitCommentsAdapter(
        token="gh-token",
        config={"repositories": ["acme/one", "acme/two"], "page_size": 1, "per_repo_limit": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=3)

    assert [signal.metadata["github_commit_comment_id"] for signal in signals] == [1, 2, 3]
    assert [request.url.path for request in requests] == [
        "/repos/acme/one/comments",
        "/repos/acme/one/comments",
        "/repos/acme/two/comments",
    ]
    assert requests[0].url.params["per_page"] == "1"
    assert requests[1].url.params["page"] == "2"


@pytest.mark.asyncio
async def test_github_commit_comments_missing_auth_or_repositories_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubCommitCommentsAdapter(config={"repositories": ["acme/api"]}).fetch() == []
    assert await GitHubCommitCommentsAdapter(token="token").fetch() == []
    assert await GitHubCommitCommentsAdapter(token="token", owner="acme", repo="api").fetch(limit=0) == []


@pytest.mark.asyncio
async def test_github_commit_comments_failure_returns_collected_signals() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/acme/one/comments":
            return httpx.Response(200, json=[{**COMMENT, "id": 1}])
        return httpx.Response(500)

    adapter = GitHubCommitCommentsAdapter(
        token="gh-token",
        config={"repositories": ["acme/one", "acme/two"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert len(signals) == 1
    assert signals[0].metadata["repository"] == "acme/one"
