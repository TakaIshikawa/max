"""Tests for the Twitter/X source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.imports.twitter_adapter import TwitterAdapter, _extract_tags
from max.sources.base import AdapterFetchError
from max.types.signal import SignalSourceType


MOCK_TWEETS_RESPONSE = {
    "data": [
        {
            "id": "tweet-001",
            "text": "Just released a new open source MCP server for AI agents! #opensource #AI",
            "created_at": "2024-04-25T10:00:00Z",
            "author_id": "user-123",
            "public_metrics": {
                "like_count": 100,
                "retweet_count": 50,
                "reply_count": 20,
            },
        },
        {
            "id": "tweet-002",
            "text": "Rust is gaining momentum in the developer tools space",
            "created_at": "2024-04-25T12:00:00Z",
            "author_id": "user-456",
            "public_metrics": {
                "like_count": 30,
                "retweet_count": 10,
                "reply_count": 5,
            },
        },
        {
            "id": "tweet-003",
            "text": "",
            "created_at": "2024-04-25T13:00:00Z",
            "author_id": "user-789",
            "public_metrics": {"like_count": 0, "retweet_count": 0, "reply_count": 0},
        },
    ]
}


def test_twitter_adapter_properties() -> None:
    adapter = TwitterAdapter()

    assert adapter.name == "twitter"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert len(adapter.queries) > 0


def test_twitter_adapter_config_overrides() -> None:
    adapter = TwitterAdapter(
        config={
            "queries": ["rust lang"],
            "watchlist_terms": ["wasm"],
            "bearer_token": "test-bearer",
        }
    )

    assert adapter.queries == ["rust lang", "wasm"]
    assert adapter._bearer_token == "test-bearer"


def test_twitter_adapter_auth_headers() -> None:
    adapter = TwitterAdapter(config={"bearer_token": "my-token"})
    headers = adapter._auth_headers()

    assert headers["Authorization"] == "Bearer my-token"


@pytest.mark.asyncio
async def test_twitter_fetch_parses_tweets() -> None:
    adapter = TwitterAdapter(config={"queries": ["AI"]})

    with patch("max.imports.twitter_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_TWEETS_RESPONSE)

        signals = await adapter.fetch(limit=10)

    # tweet-003 has empty text, should be skipped
    assert len(signals) == 2

    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "twitter"
    assert "MCP server" in first.title
    assert first.url == "https://x.com/i/status/tweet-001"
    assert first.author == "user-123"
    assert first.published_at == datetime(2024, 4, 25, 10, 0, tzinfo=timezone.utc)
    assert first.metadata["like_count"] == 100
    assert first.metadata["retweet_count"] == 50
    assert first.metadata["reply_count"] == 20
    assert first.metadata["search_query"] == "AI"
    assert first.credibility == pytest.approx(min((100 + 50 * 2 + 20) / 500, 1.0))


@pytest.mark.asyncio
async def test_twitter_fetch_deduplicates() -> None:
    adapter = TwitterAdapter(config={"queries": ["AI", "ML"]})

    with patch("max.imports.twitter_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_TWEETS_RESPONSE)

        signals = await adapter.fetch(limit=10)

    # Same tweets returned for both queries, should deduplicate
    assert len(signals) == 2
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_twitter_fetch_handles_errors() -> None:
    adapter = TwitterAdapter(config={"queries": ["AI"]})

    with patch("max.imports.twitter_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("twitter", 429, "https://api.twitter.com/2/tweets/search/recent")

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_twitter_fetch_empty_response() -> None:
    adapter = TwitterAdapter(config={"queries": ["nothing"]})

    with patch("max.imports.twitter_adapter.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"data": []})

        signals = await adapter.fetch(limit=10)

    assert signals == []


def test_extract_tags_ai() -> None:
    tags = _extract_tags("Building AI agents with MCP protocol", "AI agents")
    assert "twitter" in tags
    assert "ai-agents" in tags
    assert "ai" in tags
    assert "mcp" in tags


def test_extract_tags_open_source() -> None:
    tags = _extract_tags("New open source developer tools project released", "developer tools")
    assert "twitter" in tags
    assert "developer-tools" in tags
    assert "open-source" in tags
    assert "devtools" in tags
