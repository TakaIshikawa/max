"""Tests for Bitbucket pull request comments import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.bitbucket_pull_request_comments_adapter import BitbucketPullRequestCommentsAdapter


COMMENT = {
    "id": 1001,
    "content": {"raw": "Please add a regression test.", "markup": "markdown"},
    "user": {"display_name": "Ada", "nickname": "ada", "uuid": "{user-uuid}"},
    "state": "OPEN",
    "deleted": False,
    "inline": {"path": "src/app.py", "to": 12},
    "links": {"html": {"href": "https://bitbucket.org/example/tool/pull-requests/7/_/diff#comment-1001"}},
    "created_on": "2026-05-01T10:00:00+00:00",
    "updated_on": "2026-05-01T11:00:00+00:00",
}


@pytest.mark.asyncio
async def test_bitbucket_pull_request_comments_fetches_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "values": [COMMENT],
                    "next": "https://api.bitbucket.test/2.0/repositories/example/tool/pullrequests/7/comments?page=2",
                },
            )
        return httpx.Response(200, json={"values": [{**COMMENT, "id": 1002, "content": {"raw": "Second"}}]})

    adapter = BitbucketPullRequestCommentsAdapter(
        bearer_token="bb-token",
        api_url="https://api.bitbucket.test/2.0",
        config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7], "page_len": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb-token"
    assert requests[0].headers["User-Agent"] == "max-bitbucket-pull-request-comments-import/1"
    assert requests[0].url.path == "/2.0/repositories/example/tool/pullrequests/7/comments"
    assert requests[0].url.params["pagelen"] == "1"
    assert [signal.metadata["comment_id"] for signal in signals] == [1001, 1002]
    assert signals[0].id == "bitbucket-pr-comment:example:tool:7:1001"
    assert signals[0].source_adapter == "bitbucket_pull_request_comments_import"
    assert signals[0].content == "Please add a regression test."
    assert signals[0].url.endswith("#comment-1001")
    assert signals[0].author == "Ada"
    assert signals[0].metadata["workspace"] == "example"
    assert signals[0].metadata["repository"] == "tool"
    assert signals[0].metadata["pull_request_id"] == "7"
    assert signals[0].metadata["inline"]["path"] == "src/app.py"
    assert "comment" in signals[0].tags


@pytest.mark.asyncio
async def test_bitbucket_pull_request_comments_supports_repository_and_basic_auth_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "values": [
                    COMMENT,
                    {**COMMENT, "id": 1002, "content": {"raw": "Second"}},
                ]
            },
        )

    adapter = BitbucketPullRequestCommentsAdapter(
        config={
            "workspace": "example",
            "repository": "team/tool",
            "pull_request_ids": [7, 8],
            "username": "ada",
            "app_password": "app-pass",
        },
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    expected = "Basic " + base64.b64encode(b"ada:app-pass").decode()
    assert requests[0].headers["Authorization"] == expected
    assert requests[0].url.path == "/2.0/repositories/example/tool/pullrequests/7/comments"
    assert len(requests) == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_bitbucket_pull_request_comments_empty_without_config_auth_or_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

    assert await BitbucketPullRequestCommentsAdapter(config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7]}).fetch() == []
    assert await BitbucketPullRequestCommentsAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool"}).fetch() == []
    assert await BitbucketPullRequestCommentsAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7]}).fetch(limit=0) == []

    failing = BitbucketPullRequestCommentsAdapter(
        bearer_token="token",
        config={"workspace": "example", "repo_slug": "tool", "pull_request_ids": [7]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
