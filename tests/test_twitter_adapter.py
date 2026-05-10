"""Tests for Twitter/X source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.imports.twitter_adapter import (
    TwitterAdapter,
    _engagement_credibility,
    _extract_tags,
    _parse_datetime,
    _title_from_text,
)
from max.sources.base import AdapterFetchError, SourceAdapter
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_TWITTER_RESPONSE = {
    "data": [
        {
            "id": "1234567890",
            "text": "Building an AI agent with MCP and Claude is amazing! #ai #mcp",
            "author_id": "user_001",
            "created_at": "2026-04-10T14:00:00Z",
            "public_metrics": {
                "like_count": 250,
                "retweet_count": 80,
                "reply_count": 15,
                "quote_count": 10,
            },
        },
        {
            "id": "1234567891",
            "text": "Python 4.0 just dropped. Major changes to the type system. Thoughts?",
            "author_id": "user_002",
            "created_at": "2026-04-11T10:30:00Z",
            "public_metrics": {
                "like_count": 1500,
                "retweet_count": 400,
                "reply_count": 200,
                "quote_count": 50,
            },
        },
        {
            "id": "1234567892",
            "text": "Quick tip: use TypeScript strict mode for better DX.",
            "author_id": "user_003",
            "created_at": "2026-04-12T08:00:00Z",
            "public_metrics": {
                "like_count": 10,
                "retweet_count": 2,
                "reply_count": 1,
                "quote_count": 0,
            },
        },
    ],
}


# ── Unit Tests: _extract_tags ────────────────────────────────────────


class TestExtractTags:
    def test_includes_query_tag(self) -> None:
        tags = _extract_tags("some text", "#ai")
        assert "ai" in tags

    def test_keyword_detection(self) -> None:
        tags = _extract_tags("Using Claude and OpenAI for RAG pipelines", "#tech")
        assert "claude" in tags
        assert "openai" in tags
        assert "rag" in tags

    def test_always_includes_twitter(self) -> None:
        tags = _extract_tags("random text", "query")
        assert "twitter" in tags

    def test_limits_to_10(self) -> None:
        text = "agent llm mcp openai langchain rag embedding claude anthropic rust python typescript"
        tags = _extract_tags(text, "#everything")
        assert len(tags) <= 10

    def test_lowercases_query(self) -> None:
        tags = _extract_tags("text", "#AI")
        assert "ai" in tags


# ── Unit Tests: _parse_datetime ──────────────────────────────────────


class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4

    def test_iso_with_offset(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00+05:30")
        assert dt is not None

    def test_none_input(self) -> None:
        assert _parse_datetime(None) is None

    def test_empty_string(self) -> None:
        assert _parse_datetime("") is None

    def test_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None


# ── Unit Tests: _title_from_text ─────────────────────────────────────


class TestTitleFromText:
    def test_short_text(self) -> None:
        assert _title_from_text("Hello world") == "Hello world"

    def test_long_text_truncated(self) -> None:
        text = "x" * 200
        title = _title_from_text(text)
        assert len(title) <= 100
        assert title.endswith("...")


# ── Unit Tests: _engagement_credibility ──────────────────────────────


class TestEngagementCredibility:
    def test_zero_engagement(self) -> None:
        assert _engagement_credibility(0, 0, 0, 0) == pytest.approx(0.1)

    def test_high_engagement_caps_at_1(self) -> None:
        assert _engagement_credibility(10000, 5000, 1000, 500) == 1.0

    def test_moderate_engagement(self) -> None:
        # 250 + (80*2) + 15 + 10 = 435 -> 0.1 + 435/500 = 0.97
        cred = _engagement_credibility(250, 80, 15, 10)
        assert 0.5 < cred <= 1.0


# ── Adapter Property Tests ───────────────────────────────────────────


class TestTwitterAdapterProperties:
    def test_name(self) -> None:
        assert TwitterAdapter().name == "twitter"

    def test_source_type(self) -> None:
        assert TwitterAdapter().source_type == SignalSourceType.FORUM.value

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(TwitterAdapter(), SourceAdapter)

    def test_default_queries(self) -> None:
        a = TwitterAdapter()
        assert "#ai" in a.queries

    def test_config_overrides(self) -> None:
        a = TwitterAdapter(config={"queries": ["#rust", "#wasm"]})
        assert a.queries == ["#rust", "#wasm"]

    def test_bearer_token_env_default(self) -> None:
        assert TwitterAdapter().bearer_token_env == "TWITTER_BEARER_TOKEN"

    def test_bearer_token_env_override(self) -> None:
        a = TwitterAdapter(config={"bearer_token_env": "MY_TOKEN"})
        assert a.bearer_token_env == "MY_TOKEN"

    def test_max_results_per_query(self) -> None:
        a = TwitterAdapter(config={"max_results_per_query": 50})
        assert a.max_results_per_query == 50

    def test_max_results_capped_at_100(self) -> None:
        a = TwitterAdapter(config={"max_results_per_query": 200})
        assert a.max_results_per_query == 100


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestTwitterAdapterFetch:
    @pytest.mark.asyncio
    async def test_fetch_returns_empty_without_token(self) -> None:
        adapter = TwitterAdapter()

        with patch.dict("os.environ", {}, clear=True):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_parses_tweets(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 3
        assert signals[0].source_adapter == "twitter"
        assert signals[0].source_type == SignalSourceType.FORUM
        assert "AI agent" in signals[0].title
        assert signals[0].author == "user_001"
        assert signals[0].metadata["tweet_id"] == "1234567890"
        assert signals[0].metadata["likes"] == 250
        assert signals[0].metadata["retweets"] == 80

    @pytest.mark.asyncio
    async def test_fetch_engagement_metrics(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert signals[0].metadata["replies"] == 15
        assert signals[0].metadata["quotes"] == 10

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_deduplicates_tweets(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai", "#llm"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        # Same tweets returned for both queries, dedup by tweet_id
        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_fetch_url_format(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert signals[0].url == "https://x.com/i/status/1234567890"

    @pytest.mark.asyncio
    async def test_fetch_published_at_parsed(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert signals[0].published_at is not None
        assert signals[0].published_at.year == 2026

    @pytest.mark.asyncio
    async def test_fetch_content_truncated(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#ai"]})

        long_tweet_response = {
            "data": [
                {
                    "id": "9999",
                    "text": "x" * 1000,
                    "author_id": "user_long",
                    "created_at": "2026-04-10T00:00:00Z",
                    "public_metrics": {
                        "like_count": 0,
                        "retweet_count": 0,
                        "reply_count": 0,
                        "quote_count": 0,
                    },
                },
            ],
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = long_tweet_response
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals[0].content) <= 500


# ── Error Handling Tests ─────────────────────────────────────────────


class TestTwitterAdapterErrors:
    @pytest.mark.asyncio
    async def test_fetch_continues_on_query_error(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#bad", "#good"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_TWITTER_RESPONSE
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=[AdapterFetchError("twitter", 500, "url"), mock_resp],
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_fetch_all_fail_returns_empty(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#fail"]})

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=AdapterFetchError("twitter", 503, "url"),
            ):
                signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_handles_non_dict_response(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = "not a dict"
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_handles_missing_data_key(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"meta": {"result_count": 0}}
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_skips_tweets_without_id(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#test"]})

        response = {
            "data": [
                {
                    "text": "No ID tweet",
                    "public_metrics": {"like_count": 0, "retweet_count": 0, "reply_count": 0, "quote_count": 0},
                },
                MOCK_TWITTER_RESPONSE["data"][0],
            ],
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = response
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].metadata["tweet_id"] == "1234567890"


# ── API Call Tests ───────────────────────────────────────────────────


class TestTwitterAdapterApiCalls:
    @pytest.mark.asyncio
    async def test_uses_bearer_auth(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#test"]})

        client_headers = None

        class MockAsyncClient:
            def __init__(self, **kwargs):
                nonlocal client_headers
                client_headers = kwargs.get("headers")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "my-secret-token"}):
            with patch("max.imports.twitter_adapter.httpx.AsyncClient", MockAsyncClient):
                with patch(
                    "max.imports.twitter_adapter.fetch_with_retry",
                    new_callable=AsyncMock,
                ) as mock_fetch:
                    mock_resp = MagicMock()
                    mock_resp.json.return_value = {"data": []}
                    mock_fetch.return_value = mock_resp
                    await adapter.fetch(limit=10)

        assert client_headers is not None
        assert client_headers["Authorization"] == "Bearer my-secret-token"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self) -> None:
        adapter = TwitterAdapter(config={"queries": ["#test"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": []}
        mock_resp.status_code = 200

        with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test-token"}):
            with patch(
                "max.imports.twitter_adapter.fetch_with_retry",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ) as mock_fetch:
                await adapter.fetch(limit=10)

        call_args = mock_fetch.call_args
        assert "tweets/search/recent" in call_args.args[0]
        params = call_args.kwargs.get("params", {})
        assert params["query"] == "#test"
        assert "created_at" in params["tweet.fields"]
        assert "public_metrics" in params["tweet.fields"]
