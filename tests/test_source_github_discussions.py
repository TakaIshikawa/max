"""Tests for GitHub Discussions source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.github_discussions import (
    GitHubDiscussionsAdapter,
    _build_tags,
    _parse_dt,
    _split_repo,
)
from max.types.signal import SignalSourceType


MOCK_DISCUSSION = {
    "number": 42,
    "title": "AI agent workflow pain points",
    "bodyText": "Users are asking for better MCP server debugging in LLM agent workflows.",
    "url": "https://github.com/example/tool/discussions/42",
    "createdAt": "2026-04-10T12:00:00Z",
    "updatedAt": "2026-04-11T12:00:00Z",
    "upvoteCount": 12,
    "answerChosenAt": None,
    "category": {"name": "Ideas", "slug": "ideas"},
    "author": {"login": "maintainer"},
    "comments": {"totalCount": 6},
}


def _graphql_response(
    nodes: list[dict],
    *,
    has_next_page: bool = False,
    end_cursor: str | None = None,
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.headers = {}
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": {
            "repository": {
                "discussions": {
                    "nodes": nodes,
                    "pageInfo": {
                        "hasNextPage": has_next_page,
                        "endCursor": end_cursor,
                    },
                }
            }
        }
    }
    return resp


def test_config_parsing_normalizes_supported_keys(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_GITHUB_TOKEN", "custom-token")
    adapter = GitHubDiscussionsAdapter(
        config={
            "repositories": [" example/tool ", "example/tool", "", 42],
            "categories": [" Ideas ", "ideas"],
            "labels": [" bug ", "bug"],
            "search_terms": [" agent ", "agent"],
            "watchlist_terms": [" mcp "],
            "include_answered": False,
            "max_age_days": "14",
            "token_env": "CUSTOM_GITHUB_TOKEN",
        }
    )

    assert adapter.repositories == ["example/tool"]
    assert adapter.categories == ["Ideas", "ideas"]
    assert adapter.labels == ["bug"]
    assert adapter.search_terms == ["agent", "mcp"]
    assert adapter.include_answered is False
    assert adapter.max_age_days == 14
    assert adapter.token == "custom-token"


def test_parse_dt_and_split_repo_helpers() -> None:
    dt = _parse_dt("2026-04-11T12:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert _parse_dt("not a date") is None
    assert _split_repo("example/tool") == ("example", "tool")


def test_build_tags_extracts_keywords() -> None:
    tags = _build_tags(
        "example/mcp-python",
        {
            "title": "Agent SDK discussion",
            "bodyText": "LLM and MCP support for Python",
            "category": {"name": "Ideas"},
        },
    )
    assert "discussion" in tags
    assert "agent" in tags
    assert "llm" in tags
    assert "mcp" in tags
    assert "python" in tags


@pytest.mark.asyncio
async def test_fetch_constructs_graphql_request_and_converts_signal() -> None:
    adapter = GitHubDiscussionsAdapter(
        config={"repositories": ["example/tool"], "categories": ["ideas"]}
    )
    requests: list[dict] = []

    async def mock_post(url: str, **kwargs) -> MagicMock:
        requests.append({"url": url, **kwargs})
        return _graphql_response([MOCK_DISCUSSION])

    with patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert requests[0]["url"] == "https://api.github.com/graphql"
    variables = requests[0]["json"]["variables"]
    assert variables == {
        "owner": "example",
        "name": "tool",
        "first": 10,
        "after": None,
    }

    signal = signals[0]
    assert signal.source_type == SignalSourceType.FORUM
    assert signal.source_adapter == "github_discussions"
    assert signal.title == "AI agent workflow pain points"
    assert "MCP server debugging" in signal.content
    assert signal.url == "https://github.com/example/tool/discussions/42"
    assert signal.author == "maintainer"
    assert signal.published_at is not None
    assert "discussion" in signal.tags
    assert signal.metadata == {
        "repository": "example/tool",
        "discussion_number": 42,
        "category": "Ideas",
        "answer_count": 0,
        "comment_count": 6,
        "upvote_count": 12,
        "author": "maintainer",
        "created_at": "2026-04-10T12:00:00Z",
        "updated_at": "2026-04-11T12:00:00Z",
        "answered": False,
    }


@pytest.mark.asyncio
async def test_fetch_paginates_until_limit() -> None:
    adapter = GitHubDiscussionsAdapter(config={"repositories": ["example/tool"]})
    second = {
        **MOCK_DISCUSSION,
        "number": 43,
        "url": "https://github.com/example/tool/discussions/43",
        "title": "Second discussion",
    }
    cursors: list[str | None] = []
    responses = [
        _graphql_response([MOCK_DISCUSSION], has_next_page=True, end_cursor="cursor-1"),
        _graphql_response([second], has_next_page=True, end_cursor="cursor-2"),
    ]

    async def mock_post(url: str, **kwargs) -> MagicMock:
        cursors.append(kwargs["json"]["variables"]["after"])
        return responses.pop(0)

    with patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=2)

    assert cursors == [None, "cursor-1"]
    assert len(signals) == 2
    assert [s.metadata["discussion_number"] for s in signals] == [42, 43]


@pytest.mark.asyncio
async def test_fetch_deduplicates_by_url() -> None:
    adapter = GitHubDiscussionsAdapter(config={"repositories": ["example/tool"]})

    async def mock_post(url: str, **kwargs) -> MagicMock:
        return _graphql_response([MOCK_DISCUSSION, {**MOCK_DISCUSSION}])

    with patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_supports_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    adapter = GitHubDiscussionsAdapter(config={"repositories": ["example/tool"]})

    async def mock_post(url: str, **kwargs) -> MagicMock:
        return _graphql_response([])

    with patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_fetch_uses_default_and_configured_token_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    adapter = GitHubDiscussionsAdapter(config={"repositories": ["example/tool"]})

    async def mock_post(url: str, **kwargs) -> MagicMock:
        return _graphql_response([])

    with patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer env-token"

    monkeypatch.setenv("ALT_GITHUB_TOKEN", "alt-token")
    adapter = GitHubDiscussionsAdapter(
        config={"repositories": ["example/tool"], "token_env": "ALT_GITHUB_TOKEN"}
    )
    with patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    headers = mock_cls.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer alt-token"


@pytest.mark.asyncio
async def test_fetch_filters_terms_answered_and_age() -> None:
    adapter = GitHubDiscussionsAdapter(
        config={
            "repositories": ["example/tool"],
            "search_terms": ["mcp"],
            "include_answered": False,
            "max_age_days": 7,
        }
    )
    answered = {
        **MOCK_DISCUSSION,
        "number": 43,
        "url": "https://github.com/example/tool/discussions/43",
        "answerChosenAt": "2026-04-12T12:00:00Z",
    }
    no_term = {
        **MOCK_DISCUSSION,
        "number": 44,
        "url": "https://github.com/example/tool/discussions/44",
        "title": "Unrelated discussion",
        "bodyText": "No matching keyword",
    }

    async def mock_post(url: str, **kwargs) -> MagicMock:
        return _graphql_response([answered, no_term, MOCK_DISCUSSION])

    with patch("max.sources.github_discussions._cutoff") as mock_cutoff, \
         patch("max.sources.github_discussions.httpx.AsyncClient") as mock_cls:
        mock_cutoff.return_value = datetime(2026, 4, 9, tzinfo=timezone.utc)
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["discussion_number"] == 42
