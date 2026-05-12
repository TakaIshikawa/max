"""Tests for GitHub pull request import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_pull_requests_adapter import GitHubPullRequestsAdapter


def _pr(number: int, *, label: str = "enterprise") -> dict:
    return {
        "id": 1000 + number,
        "number": number,
        "title": f"Improve export workflow {number}",
        "body": "Adds audit context to exports.",
        "html_url": f"https://github.com/example/tool/pull/{number}",
        "state": "open",
        "user": {"login": "octocat", "id": 1, "html_url": "https://github.com/octocat"},
        "labels": [{"name": label}],
        "created_at": "2026-05-01T10:00:00Z",
        "updated_at": "2026-05-02T10:00:00Z",
        "mergeable": True,
        "draft": False,
        "review_comments": 3,
        "comments": 5,
    }


@pytest.mark.asyncio
async def test_github_pull_requests_fetch_filters_paginates_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json=[_pr(1), _pr(2, label="internal")])
        return httpx.Response(200, json=[_pr(3)])

    adapter = GitHubPullRequestsAdapter(
        token="github_token",
        api_url="https://api.github.test",
        config={
            "repositories": ["example/tool"],
            "state": "open",
            "labels": ["enterprise"],
            "per_page": 2,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer github_token"
    assert requests[0].url.path == "/repos/example/tool/pulls"
    assert requests[0].url.params["state"] == "open"
    assert requests[0].url.params["per_page"] == "2"
    assert requests[1].url.params["page"] == "2"
    assert [signal.metadata["number"] for signal in signals] == [1, 3]
    assert signals[0].source_adapter == "github_pull_requests_import"
    assert signals[0].title == "Improve export workflow 1"
    assert signals[0].url == "https://github.com/example/tool/pull/1"
    assert signals[0].author == "octocat"
    assert signals[0].metadata["repository"] == "example/tool"
    assert signals[0].metadata["state"] == "open"
    assert signals[0].metadata["labels"] == ["enterprise"]
    assert signals[0].metadata["draft"] is False
    assert signals[0].metadata["mergeable"] is True
    assert signals[0].metadata["review_count"] == 3
    assert signals[0].metadata["comment_count"] == 5
    assert "github" in signals[0].tags


@pytest.mark.asyncio
async def test_github_pull_requests_empty_without_token_repositories_or_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubPullRequestsAdapter(config={"repositories": ["example/tool"]}).fetch() == []
    assert await GitHubPullRequestsAdapter(token="token").fetch() == []
    assert (
        await GitHubPullRequestsAdapter(
            token="token", config={"repositories": ["example/tool"]}
        ).fetch(limit=0)
        == []
    )


@pytest.mark.asyncio
async def test_github_pull_requests_http_error_returns_empty() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    adapter = GitHubPullRequestsAdapter(
        token="bad",
        config={"repositories": ["example/tool"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert await adapter.fetch() == []
