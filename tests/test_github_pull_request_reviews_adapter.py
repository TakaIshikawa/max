"""Tests for GitHub pull request reviews import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.github_pull_request_reviews_adapter import GitHubPullRequestReviewsAdapter
from max.types.signal import SignalSourceType


REVIEW = {
    "id": 987,
    "node_id": "PRR_kwDOA1",
    "user": {
        "login": "octocat",
        "id": 1,
        "node_id": "MDQ6VXNlcjE=",
        "type": "User",
        "html_url": "https://github.example/octocat",
    },
    "body": "This looks ready to merge.",
    "state": "APPROVED",
    "html_url": "https://github.example/acme/api/pull/42#pullrequestreview-987",
    "pull_request_url": "https://api.github.example/repos/acme/api/pulls/42",
    "url": "https://api.github.example/repos/acme/api/pulls/42/reviews/987",
    "commit_id": "abc123",
    "submitted_at": "2026-05-01T10:00:00Z",
}


@pytest.mark.asyncio
async def test_github_pr_reviews_fetches_pages_filters_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[
                    REVIEW,
                    {**REVIEW, "id": 988, "state": "COMMENTED"},
                    {**REVIEW, "id": 989, "user": {"login": "someone-else"}},
                ],
            )
        return httpx.Response(200, json=[{**REVIEW, "id": 990, "body": "Second page"}])

    adapter = GitHubPullRequestReviewsAdapter(
        token="gh-token",
        api_url="https://github.example/api/v3",
        config={
            "repository": "acme/api",
            "pull_number": 42,
            "states": ["APPROVED"],
            "authors": ["octocat"],
            "per_page": 1,
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/v3/repos/acme/api/pulls/42/reviews"
    assert requests[0].url.params["per_page"] == "1"
    assert requests[0].url.params["page"] == "1"
    assert requests[1].url.params["page"] == "2"
    assert requests[0].headers["Authorization"] == "Bearer gh-token"
    assert requests[0].headers["Accept"] == "application/vnd.github+json"
    assert [signal.metadata["github_pull_request_review_id"] for signal in signals] == [987, 990]

    signal = signals[0]
    assert signal.id == "github-pr-review:acme/api:42:987"
    assert signal.source_type == SignalSourceType.ROADMAP
    assert signal.source_adapter == "github_pull_request_reviews_import"
    assert signal.title == "acme/api PR 42 review APPROVED"
    assert signal.content == "This looks ready to merge."
    assert signal.url == "https://github.example/acme/api/pull/42#pullrequestreview-987"
    assert signal.author == "octocat"
    assert signal.published_at is not None
    assert signal.metadata["repository"] == "acme/api"
    assert signal.metadata["pull_request_number"] == 42
    assert signal.metadata["state"] == "APPROVED"
    assert signal.metadata["body"] == "This looks ready to merge."
    assert signal.metadata["commit_id"] == "abc123"
    assert signal.metadata["submitted_at"] == "2026-05-01T10:00:00Z"
    assert signal.metadata["author"]["login"] == "octocat"
    assert signal.metadata["raw"] == REVIEW
    assert "review" in signal.tags


@pytest.mark.asyncio
async def test_github_pr_reviews_supports_targets_and_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[REVIEW])

    adapter = GitHubPullRequestReviewsAdapter(
        config={"targets": [{"repository": "acme/api", "pull_number": 42}]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Bearer env-token"
    assert requests[0].url.path == "/repos/acme/api/pulls/42/reviews"
    assert signals[0].metadata["github_pull_request_review_id"] == 987


@pytest.mark.asyncio
async def test_github_pr_reviews_multiple_repositories_and_numbers_honor_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[{**REVIEW, "id": len(requests)}])

    adapter = GitHubPullRequestReviewsAdapter(
        token="gh-token",
        config={"repositories": ["acme/api", "acme/web"], "pull_numbers": [42, 43]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].url.path == "/repos/acme/api/pulls/42/reviews"
    assert requests[1].url.path == "/repos/acme/api/pulls/43/reviews"
    assert [signal.metadata["pull_request_number"] for signal in signals] == [42, 43]


@pytest.mark.asyncio
async def test_github_pr_reviews_missing_optional_fields_and_link_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": 123,
                    "state": "COMMENTED",
                    "_links": {"html": {"href": "https://github.example/acme/api/pull/42#review-123"}},
                    "submitted_at": "2026-05-01T10:00:00Z",
                }
            ],
        )

    adapter = GitHubPullRequestReviewsAdapter(
        token="gh-token",
        repository="acme/api",
        config={"pull_number": 42},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert signals[0].author is None
    assert signals[0].content == ""
    assert signals[0].url == "https://github.example/acme/api/pull/42#review-123"
    assert signals[0].metadata["body"] == ""
    assert signals[0].metadata["author"]["login"] is None


@pytest.mark.asyncio
async def test_github_pr_reviews_empty_without_config_auth_or_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert await GitHubPullRequestReviewsAdapter(config={"repository": "acme/api", "pull_number": 42}).fetch() == []
    assert await GitHubPullRequestReviewsAdapter(token="token", repository="acme/api").fetch() == []
    assert await GitHubPullRequestReviewsAdapter(token="token", repository="acme/api", config={"pull_number": 42}).fetch(limit=0) == []

    failing = GitHubPullRequestReviewsAdapter(
        token="bad",
        repository="acme/api",
        config={"pull_number": 42},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    assert await failing.fetch() == []
