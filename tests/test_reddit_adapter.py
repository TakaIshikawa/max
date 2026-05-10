"""Tests for Reddit source adapter (imports module)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.reddit_adapter import RedditAdapter, _extract_tags
from max.sources.base import AdapterFetchError, SourceAdapter
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_REDDIT_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Building an AI Agent with MCP",
                    "selftext": "Step-by-step guide to building agents.",
                    "score": 500,
                    "url": "https://example.com/article",
                    "permalink": "/r/programming/comments/abc123/building_an_ai_agent/",
                    "author": "dev_alice",
                    "created_utc": 1712764800,
                    "num_comments": 42,
                    "stickied": False,
                },
            },
            {
                "data": {
                    "title": "Rust vs Go for CLI Tools",
                    "selftext": "Comparing Rust and Go.",
                    "score": 1200,
                    "url": "https://www.reddit.com/r/programming/comments/def456/rust_vs_go/",
                    "permalink": "/r/programming/comments/def456/rust_vs_go/",
                    "author": "rustacean",
                    "created_utc": 1712851200,
                    "num_comments": 88,
                    "stickied": False,
                },
            },
            {
                "data": {
                    "title": "Weekly Discussion Thread",
                    "selftext": "Weekly thread.",
                    "score": 10,
                    "url": "https://www.reddit.com/r/programming/comments/ghi/weekly/",
                    "permalink": "/r/programming/comments/ghi/weekly/",
                    "author": "AutoModerator",
                    "created_utc": 1712678400,
                    "num_comments": 5,
                    "stickied": True,
                },
            },
        ],
    },
}


# ── Unit Tests: _extract_tags ────────────────────────────────────────


class TestExtractTags:
    def test_subreddit_tag(self) -> None:
        tags = _extract_tags("some title", "MachineLearning")
        assert "ml" in tags

    def test_keyword_ai(self) -> None:
        tags = _extract_tags("Using Claude and LLM for coding", "programming")
        assert "ai" in tags

    def test_keyword_mcp(self) -> None:
        tags = _extract_tags("MCP protocol is great", "programming")
        assert "mcp" in tags

    def test_always_includes_reddit(self) -> None:
        tags = _extract_tags("random title", "somesubreddit")
        assert "reddit" in tags

    def test_limits_to_10(self) -> None:
        tags = _extract_tags(
            "ai llm agent mcp rust python security open source vulnerability cve exploit autonomous",
            "MachineLearning",
        )
        assert len(tags) <= 10


# ── Adapter Property Tests ───────────────────────────────────────────


class TestRedditAdapterProperties:
    def test_name(self) -> None:
        assert RedditAdapter().name == "reddit_import"

    def test_source_type(self) -> None:
        assert RedditAdapter().source_type == SignalSourceType.FORUM.value

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(RedditAdapter(), SourceAdapter)

    def test_default_subreddits(self) -> None:
        a = RedditAdapter()
        assert "programming" in a.subreddits
        assert "MachineLearning" in a.subreddits

    def test_config_overrides(self) -> None:
        a = RedditAdapter(config={"subreddits": ["rust", "golang"]})
        assert a.subreddits == ["rust", "golang"]


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestRedditAdapterFetch:
    @pytest.mark.asyncio
    async def test_fetch_parses_posts(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["programming"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_REDDIT_RESPONSE
        mock_resp.status_code = 200

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=10)

        # Stickied post should be skipped
        assert len(signals) == 2
        assert signals[0].source_adapter == "reddit_import"
        assert signals[0].source_type == SignalSourceType.FORUM
        assert "AI Agent" in signals[0].title
        assert signals[0].author == "dev_alice"
        assert signals[0].metadata["subreddit"] == "programming"
        assert signals[0].metadata["score"] == 500

    @pytest.mark.asyncio
    async def test_fetch_credibility_from_score(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["programming"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_REDDIT_RESPONSE
        mock_resp.status_code = 200

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=10)

        # 500/1000 = 0.5
        assert signals[0].credibility == pytest.approx(0.5)
        # min(1200/1000, 1.0) = 1.0
        assert signals[1].credibility == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["programming"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_REDDIT_RESPONSE
        mock_resp.status_code = 200

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_skips_stickied(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["programming"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_REDDIT_RESPONSE
        mock_resp.status_code = 200

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=10)

        titles = [s.title for s in signals]
        assert "Weekly Discussion Thread" not in titles

    @pytest.mark.asyncio
    async def test_fetch_continues_on_error(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["bad_sub", "programming"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_REDDIT_RESPONSE
        mock_resp.status_code = 200

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterFetchError("reddit_import", 500, "url"), mock_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 2

    @pytest.mark.asyncio
    async def test_fetch_all_fail_returns_empty(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["bad"]})

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=AdapterFetchError("reddit_import", 503, "url"),
        ):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_content_truncated(self) -> None:
        adapter = RedditAdapter(config={"subreddits": ["programming"]})

        response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Long post",
                            "selftext": "x" * 2000,
                            "score": 10,
                            "permalink": "/r/programming/comments/abc/long/",
                            "author": "writer",
                            "created_utc": 1712764800,
                            "num_comments": 1,
                            "stickied": False,
                        },
                    },
                ],
            },
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = response
        mock_resp.status_code = 200

        with patch(
            "max.imports.reddit_adapter.fetch_with_retry",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            signals = await adapter.fetch(limit=10)

        assert len(signals[0].content) <= 1000
