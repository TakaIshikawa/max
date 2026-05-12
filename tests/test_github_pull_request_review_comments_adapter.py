"""Tests for GitHub pull request review comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_pull_request_review_comments_adapter import GitHubPullRequestReviewCommentsAdapter
from max.types.signal import SignalSourceType


COMMENT = {
    "url": "https://api.github.example/repos/acme/api/pulls/comments/123",
    "id": 123,
    "node_id": "PRRC_kwDOA1",
    "pull_request_review_id": 456,
    "diff_hunk": "@@ -1,4 +1,4 @@",
    "path": "src/app.py",
    "position": 4,
    "original_position": 4,
    "commit_id": "abc123",
    "original_commit_id": "def456",
    "user": {
        "login": "octocat",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "type": "User",
        "html_url": "https://github.example/octocat",
    },
    "body": "Please handle the empty response case here.",
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T11:00:00Z",
    "html_url": "https://github.example/acme/api/pull/42#discussion_r123",
    "pull_request_url": "https://api.github.example/repos/acme/api/pulls/42",
}


@pytest.mark.asyncio
async def test_github_pr_review_comments_fetch_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[COMMENT])
        return httpx.Response(200, json=[{**COMMENT, "id": 124, "body": "Second page", "pull_request_url": None}])

    adapter = GitHubPullRequestReviewCommentsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={"repository": "acme/api", "per_page": 1, "sort": "created", "direction": "desc", "since": "2026-05-01T00:00:00Z"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v3/repos/acme/api/pulls/comments"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].url.params["sort"] == "created"
    assert requests[0].url.params["direction"] == "desc"
    assert requests[0].url.params["since"] == "2026-05-01T00:00:00Z"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    signal = signals[0]
    assert signal.id == "github-pr-review-comment:acme/api:123"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "github_pull_request_review_comments_import"
    assert signal.title == "acme/api PR 42 review comment"
    assert signal.content == "Please handle the empty response case here."
    assert signal.url == "https://github.example/acme/api/pull/42#discussion_r123"
    assert signal.author == "octocat"
    assert signal.metadata["repository"] == "acme/api"
    assert signal.metadata["pull_request_number"] == 42
    assert signal.metadata["comment_url"] == "https://github.example/acme/api/pull/42#discussion_r123"
    assert signal.metadata["author"]["login"] == "octocat"
    assert signal.metadata["body"] == "Please handle the empty response case here."
    assert signal.metadata["created_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["updated_at"] == "2026-05-01T11:00:00Z"
    assert "review-comment" in signal.tags
    assert signals[1].metadata["pull_request_number"] == 42


@pytest.mark.asyncio
async def test_github_pr_review_comments_empty_response_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    adapter = GitHubPullRequestReviewCommentsAdapter(
        token="gh-token",
        owner="acme",
        repo="api",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_github_pr_review_comments_missing_optional_author_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert await GitHubPullRequestReviewCommentsAdapter(config={"repository": "acme/api"}).fetch() == []
    assert await GitHubPullRequestReviewCommentsAdapter(token="token", owner="acme").fetch() == []
    assert await GitHubPullRequestReviewCommentsAdapter(token="token", owner="acme", repo="api").fetch(limit=0) == []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{k: v for k, v in COMMENT.items() if k not in {"user", "body", "pull_request_url"}}])

    adapter = GitHubPullRequestReviewCommentsAdapter(
        token="gh-token",
        repository="acme/api",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].author is None
    assert signals[0].content == ""
    assert signals[0].metadata["body"] == ""
    assert signals[0].metadata["author"]["login"] is None
    assert signals[0].metadata["pull_request_number"] == 42
