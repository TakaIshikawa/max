"""Tests for the Reddit import source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.reddit_adapter import RedditAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _reddit_listing(*posts: dict) -> dict:
    return {
        "data": {
            "children": [{"data": post} for post in posts],
        },
    }


def _post(
    title: str = "New AI framework released",
    *,
    selftext: str = "Check out this LLM agent toolkit",
    score: int = 150,
    author: str = "dev_user",
    subreddit: str = "programming",
    permalink: str = "/r/programming/comments/abc123/new_ai_framework/",
    stickied: bool = False,
    num_comments: int = 42,
    created_utc: float = 1713780000.0,
) -> dict:
    return {
        "title": title,
        "selftext": selftext,
        "score": score,
        "author": author,
        "subreddit": subreddit,
        "permalink": permalink,
        "url": f"https://www.reddit.com{permalink}",
        "stickied": stickied,
        "num_comments": num_comments,
        "created_utc": created_utc,
    }


def test_reddit_adapter_properties() -> None:
    adapter = RedditAdapter(config={"subreddits": ["rust", "golang"]})

    assert adapter.name == "reddit_import"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.subreddits == ["rust", "golang"]


def test_reddit_adapter_default_subreddits() -> None:
    adapter = RedditAdapter()
    assert "programming" in adapter.subreddits
    assert "MachineLearning" in adapter.subreddits


@pytest.mark.asyncio
async def test_reddit_fetches_posts() -> None:
    adapter = RedditAdapter(config={"subreddits": ["programming"]})

    listing = _reddit_listing(
        _post(title="AI agents are the future"),
        _post(title="New Rust compiler improvements"),
    )

    with patch("max.imports.reddit_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _response(listing)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].source_adapter == "reddit_import"
    assert signals[0].source_type == SignalSourceType.FORUM
    assert "AI agents" in signals[0].title
    assert signals[0].author == "dev_user"


@pytest.mark.asyncio
async def test_reddit_skips_stickied_posts() -> None:
    adapter = RedditAdapter(config={"subreddits": ["programming"]})

    listing = _reddit_listing(
        _post(title="Weekly Discussion Thread", stickied=True),
        _post(title="Real post about Python"),
    )

    with patch("max.imports.reddit_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _response(listing)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert "Real post" in signals[0].title


@pytest.mark.asyncio
async def test_reddit_extracts_metadata() -> None:
    adapter = RedditAdapter(config={"subreddits": ["MachineLearning"]})

    listing = _reddit_listing(
        _post(score=500, num_comments=100, subreddit="MachineLearning"),
    )

    with patch("max.imports.reddit_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _response(listing)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["subreddit"] == "MachineLearning"
    assert signals[0].metadata["score"] == 500
    assert signals[0].metadata["num_comments"] == 100
    assert signals[0].credibility == 0.5  # 500/1000


@pytest.mark.asyncio
async def test_reddit_handles_fetch_error() -> None:
    from max.sources.base import AdapterFetchError

    adapter = RedditAdapter(config={"subreddits": ["programming"]})

    with patch("max.imports.reddit_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("reddit_import", 429, "https://old.reddit.com/...")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_reddit_respects_limit() -> None:
    adapter = RedditAdapter(config={"subreddits": ["programming"]})

    listing = _reddit_listing(
        *[_post(title=f"Post {i}") for i in range(20)],
    )

    with patch("max.imports.reddit_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _response(listing)
        signals = await adapter.fetch(limit=3)

    assert len(signals) == 3


def test_reddit_tag_extraction() -> None:
    from max.imports.reddit_adapter import _extract_tags

    tags = _extract_tags("New AI agent framework with LLM support", "MachineLearning")
    assert "ml" in tags
    assert "ai" in tags
    assert "agent" in tags
