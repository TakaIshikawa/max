"""Tests for the Reddit source adapter (via imports package)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.imports.reddit_adapter import RedditAdapter
from max.types.signal import SignalSourceType


MOCK_REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "New AI framework released for Python developers",
                    "selftext": "Check out this amazing new framework for building AI agents.",
                    "score": 500,
                    "url": "https://example.com/ai-framework",
                    "permalink": "/r/programming/comments/abc123/new_ai_framework/",
                    "author": "dev_user",
                    "created_utc": 1714003200,
                    "num_comments": 45,
                    "stickied": False,
                }
            },
            {
                "data": {
                    "title": "Stickied post - rules",
                    "selftext": "Rules for the subreddit",
                    "score": 10,
                    "url": "",
                    "permalink": "/r/programming/comments/sticky/rules/",
                    "author": "mod",
                    "created_utc": 1714000000,
                    "num_comments": 0,
                    "stickied": True,
                }
            },
            {
                "data": {
                    "title": "Rust vs Go for microservices",
                    "selftext": "",
                    "score": 200,
                    "url": "https://www.reddit.com/r/programming/comments/def456/rust_vs_go/",
                    "permalink": "/r/programming/comments/def456/rust_vs_go/",
                    "author": "systems_dev",
                    "created_utc": 1714006800,
                    "num_comments": 120,
                    "stickied": False,
                }
            },
        ]
    }
}


def test_reddit_adapter_properties() -> None:
    adapter = RedditAdapter()

    assert adapter.name == "reddit"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert len(adapter.subreddits) > 0


def test_reddit_adapter_config_overrides() -> None:
    adapter = RedditAdapter(config={"subreddits": ["rust", "golang"]})

    assert "rust" in adapter.subreddits
    assert "golang" in adapter.subreddits


@pytest.mark.asyncio
async def test_reddit_fetch_parses_posts() -> None:
    adapter = RedditAdapter(config={"subreddits": ["programming"]})

    with patch("max.sources.reddit.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_REDDIT_RESPONSE)

        signals = await adapter.fetch(limit=10)

    # Should skip stickied post
    assert len(signals) == 2

    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "reddit"
    assert first.title == "New AI framework released for Python developers"
    assert first.author == "dev_user"
    assert first.published_at == datetime(2024, 4, 25, 0, 0, tzinfo=timezone.utc)
    assert first.metadata["subreddit"] == "programming"
    assert first.metadata["score"] == 500
    assert first.metadata["num_comments"] == 45
    assert first.credibility == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_reddit_fetch_handles_errors() -> None:
    from max.sources.base import AdapterFetchError

    adapter = RedditAdapter(config={"subreddits": ["badsubreddit"]})

    with patch("max.sources.reddit.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("reddit", 403, "https://old.reddit.com/r/badsubreddit/hot.json")

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_reddit_fetch_empty_response() -> None:
    adapter = RedditAdapter(config={"subreddits": ["emptysubbreddit"]})

    with patch("max.sources.reddit.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"data": {"children": []}})

        signals = await adapter.fetch(limit=10)

    assert signals == []
