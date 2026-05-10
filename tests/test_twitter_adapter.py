"""Tests for the Twitter/X source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.twitter_adapter import TwitterAdapter
from max.types.signal import SignalSourceType


def _response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def _tweet(
    tweet_id: str = "1234567890",
    *,
    text: str = "Exciting new AI agent framework just dropped!",
    likes: int = 50,
    retweets: int = 20,
    replies: int = 10,
    quotes: int = 5,
    author_id: str = "user123",
    created_at: str = "2026-04-22T10:00:00Z",
    hashtags: list[dict] | None = None,
) -> dict:
    entities: dict = {}
    if hashtags:
        entities["hashtags"] = hashtags

    return {
        "id": tweet_id,
        "text": text,
        "author_id": author_id,
        "created_at": created_at,
        "public_metrics": {
            "like_count": likes,
            "retweet_count": retweets,
            "reply_count": replies,
            "quote_count": quotes,
        },
        "entities": entities,
    }


def test_twitter_adapter_properties() -> None:
    adapter = TwitterAdapter(
        config={
            "queries": ["rust", "python"],
            "bearer_token_env": "MY_TWITTER_TOKEN",
        }
    )

    assert adapter.name == "twitter"
    assert adapter.source_type == SignalSourceType.FORUM.value
    assert adapter.queries == ["rust", "python"]
    assert adapter.bearer_token_env == "MY_TWITTER_TOKEN"


def test_twitter_adapter_defaults() -> None:
    adapter = TwitterAdapter()

    assert adapter.name == "twitter"
    assert adapter.bearer_token_env == "TWITTER_BEARER_TOKEN"
    assert len(adapter.queries) > 0


@pytest.mark.asyncio
async def test_twitter_returns_empty_without_token() -> None:
    adapter = TwitterAdapter(config={"queries": ["ai"]})
    with patch.dict("os.environ", {}, clear=True):
        signals = await adapter.fetch(limit=10)
    assert signals == []


@pytest.mark.asyncio
async def test_twitter_fetches_tweets() -> None:
    adapter = TwitterAdapter(config={"queries": ["ai agents"]})

    tweets_response = {
        "data": [
            _tweet("t1", text="AI agents are transforming development"),
            _tweet("t2", text="New MCP protocol for LLM tooling"),
        ],
    }

    with (
        patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}),
        patch("max.imports.twitter_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(tweets_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].source_adapter == "twitter"
    assert signals[0].source_type == SignalSourceType.FORUM
    assert "AI agents" in signals[0].title
    assert signals[0].url.startswith("https://x.com/i/status/")


@pytest.mark.asyncio
async def test_twitter_extracts_metrics() -> None:
    adapter = TwitterAdapter(config={"queries": ["devtools"]})

    tweets_response = {
        "data": [
            _tweet("t1", likes=200, retweets=50, replies=30, quotes=10),
        ],
    }

    with (
        patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}),
        patch("max.imports.twitter_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(tweets_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["likes"] == 200
    assert signals[0].metadata["retweets"] == 50
    assert signals[0].metadata["replies"] == 30
    assert signals[0].metadata["quotes"] == 10


@pytest.mark.asyncio
async def test_twitter_extracts_hashtags() -> None:
    adapter = TwitterAdapter(config={"queries": ["ai"]})

    tweets_response = {
        "data": [
            _tweet(
                "t1",
                text="Building #AI #Agents with #MCP",
                hashtags=[{"tag": "AI"}, {"tag": "Agents"}, {"tag": "MCP"}],
            ),
        ],
    }

    with (
        patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}),
        patch("max.imports.twitter_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(tweets_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["hashtags"] == ["ai", "agents", "mcp"]


@pytest.mark.asyncio
async def test_twitter_deduplicates_tweets() -> None:
    adapter = TwitterAdapter(config={"queries": ["ai", "ml"]})

    tweets_response = {
        "data": [_tweet("t1", text="Same tweet from both queries")],
    }

    with (
        patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}),
        patch("max.imports.twitter_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(tweets_response)
        signals = await adapter.fetch(limit=10)

    # Same tweet ID from two queries should only appear once
    assert len(signals) == 1


@pytest.mark.asyncio
async def test_twitter_handles_fetch_error() -> None:
    from max.sources.base import AdapterFetchError

    adapter = TwitterAdapter(config={"queries": ["ai"]})

    with (
        patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}),
        patch("max.imports.twitter_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.side_effect = AdapterFetchError("twitter", 429, "https://api.twitter.com/...")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_twitter_respects_limit() -> None:
    adapter = TwitterAdapter(config={"queries": ["ai"]})

    tweets_response = {
        "data": [_tweet(f"t{i}", text=f"Tweet {i}") for i in range(20)],
    }

    with (
        patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}),
        patch("max.imports.twitter_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch,
    ):
        mock_fetch.return_value = _response(tweets_response)
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 5


@pytest.mark.asyncio
async def test_twitter_returns_empty_for_zero_limit() -> None:
    adapter = TwitterAdapter(config={"queries": ["ai"]})
    with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
        signals = await adapter.fetch(limit=0)
    assert signals == []


def test_twitter_credibility_calculation() -> None:
    from max.imports.twitter_adapter import _credibility

    # Baseline
    assert _credibility(likes=0, retweets=0, replies=0) == 0.2

    # With engagement
    cred = _credibility(likes=100, retweets=50, replies=20)
    assert cred > 0.2

    # Capped at 1.0
    assert _credibility(likes=10000, retweets=5000, replies=2000) == 1.0
