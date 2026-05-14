"""Tests for Bitbucket issue comments import adapter."""

from __future__ import annotations

import base64

import httpx
import pytest

from max.imports.bitbucket_issue_comments_adapter import BitbucketIssueCommentsAdapter


COMMENT = {
    "id": 1001,
    "content": {"raw": "Issue affects onboarding.", "markup": "markdown"},
    "user": {"display_name": "Ada", "nickname": "ada", "uuid": "{user-uuid}"},
    "links": {"html": {"href": "https://bitbucket.org/example/tool/issues/9#comment-1001"}},
    "created_on": "2026-05-01T10:00:00+00:00",
    "updated_on": "2026-05-01T11:00:00+00:00",
}


@pytest.mark.asyncio
async def test_bitbucket_issue_comments_fetches_follows_next_and_maps() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"values": [COMMENT], "next": "https://api.bitbucket.test/2.0/page2"})
        return httpx.Response(200, json={"values": [{**COMMENT, "id": 1002, "content": {"raw": "Second"}}]})

    adapter = BitbucketIssueCommentsAdapter(
        bearer_token="bb-token",
        api_url="https://api.bitbucket.test/2.0",
        config={"workspace": "example", "repo_slug": "tool", "issue_ids": [9], "pagelen": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert requests[0].headers["Authorization"] == "Bearer bb-token"
    assert requests[0].url.path == "/2.0/repositories/example/tool/issues/9/comments"
    assert requests[0].url.params["pagelen"] == "1"
    assert [signal.metadata["comment_id"] for signal in signals] == [1001, 1002]
    assert signals[0].id == "bitbucket-issue-comment:example:tool:9:1001"
    assert signals[0].source_adapter == "bitbucket_issue_comments_import"
    assert signals[0].content == "Issue affects onboarding."
    assert signals[0].author == "Ada"
    assert signals[0].metadata["issue_id"] == "9"


@pytest.mark.asyncio
async def test_bitbucket_issue_comments_supports_basic_auth_repository_and_limit() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"values": [COMMENT, {**COMMENT, "id": 1002}]})

    adapter = BitbucketIssueCommentsAdapter(
        config={"workspace": "example", "repository": "team/tool", "issue_ids": [9, 10], "username": "ada", "app_password": "pass"},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=1)

    assert requests[0].headers["Authorization"] == "Basic " + base64.b64encode(b"ada:pass").decode()
    assert requests[0].url.path == "/2.0/repositories/example/tool/issues/9/comments"
    assert len(requests) == 1
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_bitbucket_issue_comments_empty_without_config_auth_or_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BITBUCKET_USERNAME", raising=False)
    monkeypatch.delenv("BITBUCKET_APP_PASSWORD", raising=False)
    monkeypatch.delenv("BITBUCKET_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)

    assert await BitbucketIssueCommentsAdapter(config={"workspace": "example", "repo_slug": "tool", "issue_ids": [9]}).fetch() == []
    assert await BitbucketIssueCommentsAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool"}).fetch() == []
    assert await BitbucketIssueCommentsAdapter(bearer_token="token", config={"workspace": "example", "repo_slug": "tool", "issue_ids": [9]}).fetch(limit=0) == []

    failing = BitbucketIssueCommentsAdapter(
        bearer_token="token",
        config={"workspace": "example", "repo_slug": "tool", "issue_ids": [9]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    assert await failing.fetch(limit=2) == []
