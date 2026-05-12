"""Tests for Sentry issue comments import adapter."""

from __future__ import annotations

import httpx
import pytest

from max.imports.sentry_issue_comments_adapter import SentryIssueCommentsAdapter
from max.types.signal import SignalSourceType


def _comment(comment_id: str) -> dict:
    return {
        "id": comment_id,
        "data": f"Investigating customer impact {comment_id}",
        "dateCreated": "2026-05-02T12:00:00Z",
        "user": {
            "id": "u1",
            "name": "Ada Lovelace",
            "username": "ada",
            "email": "ada@example.com",
        },
        "issueUrl": "https://sentry.example/issues/123/",
        "permalink": f"https://sentry.example/issues/123/comments/{comment_id}/",
    }


@pytest.mark.asyncio
async def test_sentry_issue_comments_fetches_cursor_pages_and_maps_comments() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json=[_comment("c1")],
                headers={
                    "Link": '<https://sentry.example/api/0/issues/123/comments/?cursor=next-cursor>; rel="next"; results="true"; cursor="next-cursor"'
                },
            )
        return httpx.Response(
            200,
            json=[_comment("c2")],
            headers={
                "Link": '<https://sentry.example/api/0/issues/123/comments/?cursor=end>; rel="next"; results="false"; cursor="end"'
            },
        )

    adapter = SentryIssueCommentsAdapter(
        auth_token="sentry-token",
        api_url="https://sentry.example/api/0",
        config={"issue_ids": ["123"], "page_size": 1, "include_user_metadata": True},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert requests[0].url.path == "/api/0/issues/123/comments/"
    assert requests[0].url.params["per_page"] == "1"
    assert "cursor" not in requests[0].url.params
    assert requests[1].url.params["cursor"] == "next-cursor"
    assert requests[0].headers["Authorization"] == "Bearer sentry-token"
    assert [signal.metadata["sentry_comment_id"] for signal in signals] == ["c1", "c2"]
    signal = signals[0]
    assert signal.id == "sentry-issue-comment:123:c1"
    assert signal.source_type == SignalSourceType.FAILURE_DATA
    assert signal.source_adapter == "sentry_issue_comments_import"
    assert signal.title == "Sentry issue 123 comment"
    assert signal.content == "Investigating customer impact c1"
    assert signal.url == "https://sentry.example/issues/123/comments/c1/"
    assert signal.author == "Ada Lovelace"
    assert signal.metadata["sentry_issue_id"] == "123"
    assert signal.metadata["message"] == "Investigating customer impact c1"
    assert signal.metadata["issue_url"] == "https://sentry.example/issues/123/"
    assert signal.metadata["comment_url"] == "https://sentry.example/issues/123/comments/c1/"
    assert signal.metadata["user"]["username"] == "ada"
    assert signal.metadata["user_metadata"]["email"] == "ada@example.com"
    assert signal.metadata["raw"]["id"] == "c1"
    assert "issue-comment" in signal.tags


@pytest.mark.asyncio
async def test_sentry_issue_comments_respects_limits_across_issues() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[_comment(str(len(requests)))])

    adapter = SentryIssueCommentsAdapter(
        token="sentry-token",
        config={"issue_ids": ["1", "2"], "per_issue_limit": 1},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=2)

    assert len(requests) == 2
    assert [signal.metadata["sentry_issue_id"] for signal in signals] == ["1", "2"]


@pytest.mark.asyncio
async def test_sentry_issue_comments_empty_without_required_config_or_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SENTRY_AUTH_TOKEN", raising=False)

    assert await SentryIssueCommentsAdapter(config={"issue_ids": ["1"]}).fetch() == []
    assert await SentryIssueCommentsAdapter(auth_token="token").fetch() == []
    assert await SentryIssueCommentsAdapter(auth_token="token", config={"issue_ids": ["1"]}).fetch(limit=0) == []


@pytest.mark.asyncio
async def test_sentry_issue_comments_failure_returns_partial_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/issues/1/comments/"):
            return httpx.Response(200, json=[_comment("c1")])
        return httpx.Response(500)

    adapter = SentryIssueCommentsAdapter(
        auth_token="sentry-token",
        config={"issue_ids": ["1", "2"]},
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    signals = await adapter.fetch(limit=5)

    assert len(requests) == 2
    assert [signal.metadata["sentry_comment_id"] for signal in signals] == ["c1"]
