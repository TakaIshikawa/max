"""Tests for GitHub issue comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_issue_comments_adapter import GitHubIssueCommentsAdapter


COMMENT = {
    "id": 1001,
    "node_id": "IC_kwDOA1",
    "body": "Customers need this workflow.",
    "user": {"login": "octocat", "id": 1, "type": "User", "html_url": "https://github.example/octocat"},
    "created_at": "2026-05-01T10:00:00Z",
    "updated_at": "2026-05-01T10:05:00Z",
    "html_url": "https://github.example/acme/api/issues/42#issuecomment-1001",
    "url": "https://api.github.example/repos/acme/api/issues/comments/1001",
    "issue_url": "https://api.github.example/repos/acme/api/issues/42",
}


@pytest.mark.asyncio
async def test_github_issue_comments_fetches_paginates_across_issues_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/issues/42/comments"):
            return httpx.Response(200, json=[COMMENT])
        return httpx.Response(200, json=[{**COMMENT, "id": 1002, "body": "Second issue"}])

    adapter = GitHubIssueCommentsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={"repository": "acme/api", "issue_numbers": [42, 43], "per_page": 2},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert requests[0].headers["User-Agent"] == "max-github-issue-comments-import/1"
    assert requests[0].url.path == "/api/v3/repos/acme/api/issues/42/comments"
    assert requests[0].url.params["page"] == "1"
    assert requests[0].url.params["per_page"] == "2"
    assert signals[0].id == "github-issue-comment:acme/api:42:1001"
    assert signals[0].source_adapter == "github_issue_comments_import"
    assert signals[0].content == "Customers need this workflow."
    assert signals[0].url.endswith("#issuecomment-1001")
    assert signals[0].author == "octocat"
    assert signals[0].metadata["repository"] == "acme/api"
    assert signals[0].metadata["issue_number"] == 42
    assert signals[0].metadata["raw"] == COMMENT


@pytest.mark.asyncio
async def test_github_issue_comments_supports_owner_repo_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params["page"] == "1":
            return httpx.Response(200, json=[{**COMMENT, "id": 1}])
        return httpx.Response(200, json=[{**COMMENT, "id": 2}])

    adapter = GitHubIssueCommentsAdapter(
        token="gh-token",
        owner="acme",
        repo="api",
        config={"issue_numbers": "42", "per_page": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert [request.url.params["page"] for request in requests] == ["1", "2"]
    assert [signal.metadata["github_issue_comment_id"] for signal in signals] == [1, 2]


@pytest.mark.asyncio
async def test_github_issue_comments_empty_without_config_auth_or_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubIssueCommentsAdapter(config={"repository": "acme/api", "issue_numbers": [42]}).fetch() == []
    assert await GitHubIssueCommentsAdapter(token="token", config={"issue_numbers": [42]}).fetch() == []
    assert await GitHubIssueCommentsAdapter(token="token", config={"repository": "acme/api"}).fetch() == []
    assert await GitHubIssueCommentsAdapter(token="token", config={"repository": "acme/api", "issue_numbers": [42]}).fetch(limit=0) == []

    failing = GitHubIssueCommentsAdapter(
        token="bad",
        config={"repository": "acme/api", "issue_numbers": [42]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=1) == []
