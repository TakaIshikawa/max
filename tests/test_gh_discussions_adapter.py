"""Tests for GitHub Discussions import adapter — community Q&A signals."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.gh_discussions_adapter import (
    GHDiscussionsAdapter,
    _build_tags,
    _compute_credibility,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_DISCUSSION = {
    "id": "D_kwDOAe5Yuc4AXXYZ",
    "title": "RFC: New routing API",
    "body": "Proposing a new file-based routing system with better nested layouts.",
    "url": "https://github.com/vercel/next.js/discussions/12345",
    "createdAt": "2024-03-10T10:00:00Z",
    "author": {"login": "contributor1"},
    "category": {"name": "RFC"},
    "upvoteCount": 25,
    "comments": {"totalCount": 18},
    "answer": {"id": "ans-001"},
    "labels": {"nodes": [{"name": "enhancement"}, {"name": "routing"}]},
}

MOCK_DISCUSSION_2 = {
    "id": "D_kwDOAe5Yuc4AXXZZ",
    "title": "Help: How to use server components?",
    "body": "I'm confused about when to use server vs client components.",
    "url": "https://github.com/vercel/next.js/discussions/12346",
    "createdAt": "2024-03-09T08:00:00Z",
    "author": {"login": "newdev"},
    "category": {"name": "Q&A"},
    "upvoteCount": 5,
    "comments": {"totalCount": 3},
    "answer": None,
    "labels": {"nodes": []},
}

MOCK_GRAPHQL_RESPONSE = {
    "data": {
        "repository": {
            "discussions": {
                "nodes": [MOCK_DISCUSSION, MOCK_DISCUSSION_2],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
}

MOCK_EMPTY_RESPONSE = {
    "data": {
        "repository": {
            "discussions": {
                "nodes": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }
    }
}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2024-03-10T10:00:00+00:00")
    assert dt is not None
    assert dt.year == 2024


def test_parse_dt_zulu() -> None:
    dt = _parse_dt("2024-03-10T10:00:00Z")
    assert dt is not None


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_build_tags_answered() -> None:
    tags = _build_tags(MOCK_DISCUSSION)
    assert "github" in tags
    assert "discussions" in tags
    assert "answered" in tags
    assert "rfc" in tags
    assert "enhancement" in tags


def test_build_tags_unanswered() -> None:
    tags = _build_tags(MOCK_DISCUSSION_2)
    assert "github" in tags
    assert "discussions" in tags
    assert "answered" not in tags
    assert "q&a" in tags


def test_compute_credibility_high() -> None:
    score = _compute_credibility({"upvoteCount": 50, "comments": {"totalCount": 25}})
    assert score == 1.0


def test_compute_credibility_low() -> None:
    score = _compute_credibility({"upvoteCount": 0, "comments": {"totalCount": 0}})
    assert score == 0.1


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = GHDiscussionsAdapter()
    assert adapter.name == "gh_discussions_import"


def test_adapter_source_type() -> None:
    adapter = GHDiscussionsAdapter()
    assert adapter.source_type == SignalSourceType.FORUM.value


def test_adapter_default_repos() -> None:
    adapter = GHDiscussionsAdapter()
    assert "vercel/next.js" in adapter.repos


def test_adapter_custom_repos() -> None:
    adapter = GHDiscussionsAdapter(config={"repos": ["myorg/myrepo"]})
    assert adapter.repos == ["myorg/myrepo"]


def test_adapter_query() -> None:
    adapter = GHDiscussionsAdapter(config={"query": "facebook/react"})
    assert adapter.query == "facebook/react"


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_discussions() -> None:
    adapter = GHDiscussionsAdapter(config={
        "query": "vercel/next.js",
        "token": "ghp_test123",
    })

    with patch(
        "max.imports.gh_discussions_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_GRAPHQL_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "RFC: New routing API"
    assert sig.source_adapter == "gh_discussions_import"
    assert sig.source_type == SignalSourceType.FORUM
    assert sig.author == "contributor1"
    assert sig.metadata["upvotes"] == 25
    assert sig.metadata["comment_count"] == 18
    assert sig.metadata["is_answered"] is True
    assert sig.metadata["repo"] == "vercel/next.js"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = GHDiscussionsAdapter(config={
        "query": "vercel/next.js",
        "token": "ghp_test123",
    })

    with patch(
        "max.imports.gh_discussions_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_GRAPHQL_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_no_token() -> None:
    adapter = GHDiscussionsAdapter(config={"query": "vercel/next.js"})

    with patch(
        "max.imports.gh_discussions_adapter._get_token",
        return_value=None,
    ):
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = GHDiscussionsAdapter(config={
        "query": "vercel/next.js",
        "token": "ghp_test123",
    })

    with patch(
        "max.imports.gh_discussions_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = GHDiscussionsAdapter(config={
        "query": "vercel/next.js",
        "token": "ghp_test123",
    })

    with patch(
        "max.imports.gh_discussions_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {
        "data": {
            "repository": {
                "discussions": {
                    "nodes": [MOCK_DISCUSSION, MOCK_DISCUSSION],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }
    }
    adapter = GHDiscussionsAdapter(config={
        "query": "vercel/next.js",
        "token": "ghp_test123",
    })

    with patch(
        "max.imports.gh_discussions_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
