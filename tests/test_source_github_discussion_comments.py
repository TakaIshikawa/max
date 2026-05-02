"""Tests for GitHub Discussion Comments source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.github_discussion_comments import (
    GitHubDiscussionCommentsAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


MOCK_DISCUSSION = {
    "number": 42,
    "title": "AI agent workflow pain points",
    "url": "https://github.com/example/tool/discussions/42",
    "category": {"name": "Ideas", "slug": "ideas"},
    "labels": {"nodes": [{"name": "bug"}, {"name": "mcp"}]},
}

MOCK_COMMENT = {
    "id": "DC_kwDOExample",
    "bodyText": "The MCP server debugging flow is painful for agent users.",
    "url": "https://github.com/example/tool/discussions/42#discussioncomment-1",
    "createdAt": "2026-04-10T12:00:00Z",
    "updatedAt": "2026-04-11T12:00:00Z",
    "upvoteCount": 7,
    "author": {"login": "user-one"},
}


def _graphql_response(
    comments: list[dict],
    *,
    discussion: dict | None = MOCK_DISCUSSION,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    if discussion is None:
        discussion_payload = None
    else:
        discussion_payload = {
            **discussion,
            "comments": {
                "totalCount": len(comments),
                "nodes": comments,
                "pageInfo": {
                    "hasNextPage": has_next_page,
                    "endCursor": end_cursor,
                },
            },
        }
    resp.json.return_value = {
        "data": {
            "repository": {
                "discussion": discussion_payload,
            }
        }
    }
    return resp


def test_config_parsing_and_helpers(monkeypatch) -> None:
    monkeypatch.setenv("ALT_GITHUB_TOKEN", "env-token")
    adapter = GitHubDiscussionCommentsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", "", 42],
            "discussion_numbers": {"example/tool": ["42", 42, "bad", 0]},
            "labels": [" bug ", "bug"],
            "api_url": " https://github.example/api ",
            "max_comments_per_discussion": "25",
            "token_env": "ALT_GITHUB_TOKEN",
        }
    )

    assert adapter.repositories == ["example/tool"]
    assert adapter.discussion_numbers == {"example/tool": [42]}
    assert adapter.labels == ["bug"]
    assert adapter.api_url == "https://github.example/api"
    assert adapter.max_comments_per_discussion == 25
    assert adapter.token == "env-token"
    assert _parse_dt("2026-04-10T12:00:00Z") is not None
    assert _parse_dt("not-a-date") is None


def test_build_tags_extracts_comment_keywords() -> None:
    tags = _build_tags(
        "example/mcp-python",
        "Agent SDK discussion",
        "Painful LLM and MCP debugging for Python users",
        ["bug"],
        {"name": "Ideas"},
    )
    assert "discussion-comment" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags
    assert "python" in tags


@pytest.mark.asyncio
async def test_fetch_converts_discussion_comments_to_signals() -> None:
    adapter = GitHubDiscussionCommentsAdapter(
        config={
            "repositories": ["example/tool"],
            "discussion_numbers": [42],
            "labels": ["bug"],
            "github_token": "configured-token",
        }
    )
    requests: list[dict] = []

    async def mock_fetch(url: str, client, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _graphql_response([MOCK_COMMENT])

    with patch("max.sources.github_discussion_comments.fetch_with_retry", mock_fetch), \
         patch("max.sources.github_discussion_comments.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert requests[0]["url"] == "https://api.github.com/graphql"
    assert requests[0]["adapter_name"] == "github_discussion_comments"
    assert requests[0]["method"] == "POST"
    assert requests[0]["json"]["variables"] == {
        "owner": "example",
        "name": "tool",
        "number": 42,
        "first": 10,
        "after": None,
    }
    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer configured-token"

    signal = signals[0]
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.source_adapter == "github_discussion_comments"
    assert signal.title == "Comment on AI agent workflow pain points"
    assert "debugging flow is painful" in signal.content
    assert signal.url.endswith("#discussioncomment-1")
    assert signal.author == "user-one"
    assert signal.published_at is not None
    assert "discussion-comment" in signal.tags
    assert signal.metadata == {
        "repository": "example/tool",
        "discussion_number": 42,
        "discussion_title": "AI agent workflow pain points",
        "discussion_url": "https://github.com/example/tool/discussions/42",
        "comment_id": "DC_kwDOExample",
        "category": "Ideas",
        "labels": ["bug", "mcp"],
        "upvote_count": 7,
        "author": "user-one",
        "created_at": "2026-04-10T12:00:00Z",
        "updated_at": "2026-04-11T12:00:00Z",
        "signal_role": "problem",
    }
    assert "configured-token" not in repr(signal.metadata)


@pytest.mark.asyncio
async def test_fetch_fans_out_per_discussion_and_paginates() -> None:
    adapter = GitHubDiscussionCommentsAdapter(
        config={
            "repositories": ["example/tool"],
            "discussion_numbers": {"example/tool": [42, 43]},
            "max_comments_per_discussion": 2,
        }
    )
    second_comment = {
        **MOCK_COMMENT,
        "id": "DC_second",
        "url": "https://github.com/example/tool/discussions/42#discussioncomment-2",
    }
    third_comment = {
        **MOCK_COMMENT,
        "id": "DC_third",
        "url": "https://github.com/example/tool/discussions/43#discussioncomment-3",
    }
    responses = [
        _graphql_response([MOCK_COMMENT], has_next_page=True, end_cursor="cursor-1"),
        _graphql_response([second_comment]),
        _graphql_response([third_comment], discussion={**MOCK_DISCUSSION, "number": 43}),
    ]
    variables: list[dict] = []

    async def mock_fetch(url: str, client, **kwargs) -> MagicMock:
        variables.append(kwargs["json"]["variables"])
        return responses.pop(0)

    with patch("max.sources.github_discussion_comments.fetch_with_retry", mock_fetch):
        signals = await adapter.fetch(limit=10)

    assert [item["number"] for item in variables] == [42, 42, 43]
    assert [item["after"] for item in variables] == [None, "cursor-1", None]
    assert len(signals) == 3
    assert [signal.metadata["comment_id"] for signal in signals] == [
        "DC_kwDOExample",
        "DC_second",
        "DC_third",
    ]


@pytest.mark.asyncio
async def test_fetch_empty_config_returns_empty_without_http() -> None:
    adapter = GitHubDiscussionCommentsAdapter(config={})

    with patch("max.sources.github_discussion_comments.fetch_with_retry") as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert signals == []
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_empty_results_and_label_mismatch_return_empty() -> None:
    adapter = GitHubDiscussionCommentsAdapter(
        config={"repositories": ["example/tool"], "discussion_numbers": [42]}
    )

    async def mock_empty(url: str, client, **kwargs) -> MagicMock:
        return _graphql_response([])

    with patch("max.sources.github_discussion_comments.fetch_with_retry", mock_empty):
        assert await adapter.fetch(limit=10) == []

    adapter = GitHubDiscussionCommentsAdapter(
        config={
            "repositories": ["example/tool"],
            "discussion_numbers": [42],
            "labels": ["security"],
        }
    )

    async def mock_label_mismatch(url: str, client, **kwargs) -> MagicMock:
        return _graphql_response([MOCK_COMMENT])

    with patch("max.sources.github_discussion_comments.fetch_with_retry", mock_label_mismatch):
        assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_fetch_http_failure_is_handled() -> None:
    adapter = GitHubDiscussionCommentsAdapter(
        config={"repositories": ["example/tool"], "discussion_numbers": [42]}
    )

    async def mock_failure(url: str, client, **kwargs) -> MagicMock:
        raise httpx.TimeoutException("timeout")

    import httpx

    with patch("max.sources.github_discussion_comments.fetch_with_retry", mock_failure):
        signals = await adapter.fetch(limit=10)

    assert signals == []
