"""Comprehensive tests for Dev.to source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
    SourceAdapter,
)
from max.sources.devto import (
    DevtoAdapter,
    _extract_tags,
    _parse_datetime,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_DEVTO_ARTICLES = [
    {
        "id": 1001,
        "title": "Building an AI Agent with MCP and Claude",
        "description": "A step-by-step guide to building AI agents using MCP servers.",
        "url": "https://dev.to/alice/building-ai-agent-mcp",
        "published_at": "2026-04-10T14:00:00Z",
        "positive_reactions_count": 75,
        "comments_count": 12,
        "reading_time_minutes": 8,
        "tag_list": ["ai", "mcp", "python"],
        "user": {"name": "Alice Dev"},
    },
    {
        "id": 1002,
        "title": "RAG Pipeline Best Practices for 2026",
        "description": "What I learned building production RAG systems.",
        "url": "https://dev.to/bob/rag-best-practices",
        "published_at": "2026-04-11T10:30:00Z",
        "positive_reactions_count": 150,
        "comments_count": 25,
        "reading_time_minutes": 12,
        "tag_list": ["rag", "llm", "embedding"],
        "user": {"name": "Bob ML"},
    },
    {
        "id": 1003,
        "title": "TypeScript Tips for CLI Tools",
        "description": "Quick tips for building CLI tools.",
        "url": "https://dev.to/charlie/ts-cli-tips",
        "published_at": "2026-04-12T08:00:00Z",
        "positive_reactions_count": 30,
        "comments_count": 5,
        "reading_time_minutes": 4,
        "tag_list": ["typescript", "cli"],
        "user": {"name": "Charlie TS"},
    },
]


# ── Unit Tests: _extract_tags ────────────────────────────────────────


class TestExtractTags:
    def test_includes_article_tags(self) -> None:
        tags = _extract_tags(["ai", "mcp", "python"], "some title")
        assert "ai" in tags
        assert "mcp" in tags
        assert "python" in tags

    def test_extracts_keywords_from_title(self) -> None:
        tags = _extract_tags([], "Building an agent with LangChain for RAG")
        assert "agent" in tags
        assert "langchain" in tags
        assert "rag" in tags

    def test_always_includes_devto(self) -> None:
        tags = _extract_tags([], "random title")
        assert "devto" in tags

    def test_limits_to_10(self) -> None:
        many_tags = [f"tag-{i}" for i in range(15)]
        tags = _extract_tags(many_tags, "agent llm mcp rag embedding openai claude")
        assert len(tags) <= 10

    def test_lowercases_tags(self) -> None:
        tags = _extract_tags(["AI", "MCP"], "title")
        assert "ai" in tags
        assert "mcp" in tags

    def test_keyword_openai(self) -> None:
        tags = _extract_tags([], "Using OpenAI API for chat")
        assert "openai" in tags

    def test_keyword_claude(self) -> None:
        tags = _extract_tags([], "Building with Claude and Anthropic SDK")
        assert "claude" in tags
        assert "anthropic" in tags

    def test_keyword_embedding(self) -> None:
        tags = _extract_tags([], "Embedding models comparison")
        assert "embedding" in tags

    def test_takes_first_8_article_tags(self) -> None:
        tags_10 = [f"t{i}" for i in range(10)]
        result = _extract_tags(tags_10, "title")
        assert "t8" not in result
        assert "t9" not in result


# ── Unit Tests: _parse_datetime ──────────────────────────────────────


class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 10

    def test_iso_with_offset(self) -> None:
        dt = _parse_datetime("2026-04-10T14:00:00+05:30")
        assert dt is not None
        assert dt.year == 2026

    def test_none_input(self) -> None:
        assert _parse_datetime(None) is None

    def test_empty_string(self) -> None:
        assert _parse_datetime("") is None

    def test_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None


# ── Adapter Property Tests ───────────────────────────────────────────


class TestDevtoAdapterProperties:
    def test_name(self) -> None:
        assert DevtoAdapter().name == "devto"

    def test_source_type(self) -> None:
        assert DevtoAdapter().source_type == SignalSourceType.FORUM.value

    def test_config_defaults(self) -> None:
        a = DevtoAdapter()
        assert "ai" in a.tags
        assert a.period == 7

    def test_config_overrides(self) -> None:
        a = DevtoAdapter(config={"tags": ["rust", "wasm"], "period": 14})
        assert a.tags == ["rust", "wasm"]
        assert a.period == 14

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(DevtoAdapter(), SourceAdapter)

    def test_accepts_config(self) -> None:
        config = {"tags": ["test"], "period": 30}
        a = DevtoAdapter(config=config)
        assert a._config == config

    def test_no_config(self) -> None:
        a = DevtoAdapter()
        assert a._config == {}


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestDevtoAdapterFetch:
    @pytest.mark.asyncio
    async def test_fetch_parses_articles(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 3
        assert signals[0].source_adapter == "devto"
        assert signals[0].source_type == SignalSourceType.FORUM
        assert "AI Agent" in signals[0].title
        assert signals[0].url == "https://dev.to/alice/building-ai-agent-mcp"
        assert signals[0].author == "Alice Dev"
        assert signals[0].metadata["devto_id"] == 1001

    @pytest.mark.asyncio
    async def test_fetch_credibility_from_reactions(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        # 75 reactions -> 75/100 = 0.75
        assert signals[0].credibility == pytest.approx(0.75)
        # 150 reactions -> min(150/100, 1.0) = 1.0
        assert signals[1].credibility == pytest.approx(1.0)
        # 30 reactions -> 30/100 = 0.3
        assert signals[2].credibility == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_fetch_credibility_zero_reactions(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [{
            "id": 5001,
            "title": "Test",
            "description": "desc",
            "url": "https://dev.to/test",
            "published_at": "2026-04-10T00:00:00Z",
            "positive_reactions_count": 0,
            "comments_count": 0,
            "reading_time_minutes": 1,
            "tag_list": [],
            "user": {"name": "Nobody"},
        }]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals[0].credibility == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_deduplicates_across_tags(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai", "llm", "mcp"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = MOCK_DEVTO_ARTICLES
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        # Same articles returned for all tags, dedup by devto_id
        assert len(signals) == 3

    @pytest.mark.asyncio
    async def test_fetch_handles_tag_list_as_string(self) -> None:
        """Some Dev.to responses return tag_list as comma-separated string."""
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [{
            "id": 2001,
            "title": "Test Article",
            "description": "Test desc",
            "url": "https://dev.to/test",
            "published_at": "2026-04-10T00:00:00Z",
            "positive_reactions_count": 10,
            "comments_count": 1,
            "reading_time_minutes": 3,
            "tag_list": "python, ai, tools",
            "user": {"name": "Tester"},
        }]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert "python" in signals[0].tags or "ai" in signals[0].tags

    @pytest.mark.asyncio
    async def test_fetch_content_truncated_to_500(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [{
            "id": 3001,
            "title": "Long Article",
            "description": "x" * 1000,
            "url": "https://dev.to/test/long",
            "published_at": "2026-04-10T00:00:00Z",
            "positive_reactions_count": 10,
            "comments_count": 0,
            "reading_time_minutes": 5,
            "tag_list": [],
            "user": {"name": "Writer"},
        }]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals[0].content) <= 500

    @pytest.mark.asyncio
    async def test_fetch_missing_description(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [{
            "id": 3002,
            "title": "No Description",
            "url": "https://dev.to/test/no-desc",
            "published_at": "2026-04-10T00:00:00Z",
            "positive_reactions_count": 5,
            "comments_count": 0,
            "reading_time_minutes": 2,
            "tag_list": [],
            "user": {"name": "Writer"},
        }]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].content == ""

    @pytest.mark.asyncio
    async def test_fetch_missing_user(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [{
            "id": 3003,
            "title": "No User",
            "description": "desc",
            "url": "https://dev.to/test/no-user",
            "published_at": "2026-04-10T00:00:00Z",
            "positive_reactions_count": 5,
            "comments_count": 0,
            "reading_time_minutes": 2,
            "tag_list": [],
        }]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].author is None

    @pytest.mark.asyncio
    async def test_fetch_skips_articles_without_id(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        articles = [
            {
                "title": "No ID Article",
                "description": "desc",
                "url": "https://dev.to/test/no-id",
                "published_at": "2026-04-10T00:00:00Z",
                "positive_reactions_count": 5,
                "comments_count": 0,
                "reading_time_minutes": 2,
                "tag_list": [],
                "user": {"name": "User"},
            },
            MOCK_DEVTO_ARTICLES[0],
        ]

        mock_resp = MagicMock()
        mock_resp.json.return_value = articles
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].metadata["devto_id"] == 1001

    @pytest.mark.asyncio
    async def test_fetch_metadata_fields(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        meta = signals[0].metadata
        assert meta["devto_id"] == 1001
        assert meta["reactions"] == 75
        assert meta["comments"] == 12
        assert meta["reading_time"] == 8
        assert meta["tag_list"] == ["ai", "mcp", "python"]

    @pytest.mark.asyncio
    async def test_fetch_published_at_parsed(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals[0].published_at is not None
        assert signals[0].published_at.year == 2026
        assert signals[0].published_at.month == 4
        assert signals[0].published_at.day == 10

    @pytest.mark.asyncio
    async def test_fetch_calls_api_with_correct_params(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai"], "period": 14})

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            await adapter.fetch(limit=10)

        call_args = mock_fetch.call_args
        assert call_args.args[0] == "https://dev.to/api/articles"
        params = call_args.kwargs.get("params") or call_args[1].get("params", {})
        assert params["tag"] == "ai"
        assert params["top"] == 14
        assert call_args.kwargs.get("adapter_name") == "devto"

    @pytest.mark.asyncio
    async def test_fetch_sleeps_between_tags(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["ai", "llm"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await adapter.fetch(limit=10)

        mock_sleep.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_fetch_skips_non_list_response(self) -> None:
        """Adapter skips response when JSON is not a list."""
        adapter = DevtoAdapter(config={"tags": ["ai"]})

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "not found"}
        mock_resp.status_code = 200

        with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals == []


# ── Error Handling Tests ─────────────────────────────────────────────


class TestDevtoAdapterErrors:
    @pytest.mark.asyncio
    async def test_fetch_continues_on_tag_error(self) -> None:
        """Adapter logs warning and continues when a tag fetch fails."""
        adapter = DevtoAdapter(config={"tags": ["bad_tag", "good_tag"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterFetchError("devto", 500, "url"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_rate_limit(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["t1", "t2"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterRateLimitError("devto", "url"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_circuit_open(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["t1", "t2"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterCircuitOpenError("devto", retry_after=60.0), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_timeout(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["t1", "t2"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[httpx.TimeoutException("timeout"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_connect_error(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["t1", "t2"]})

        mock_good_resp = MagicMock()
        mock_good_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[httpx.ConnectError("conn failed"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_all_tags_fail_returns_empty(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["t1"]})

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=AdapterFetchError("devto", 503, "url"),
        ):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_handles_json_parse_error(self) -> None:
        """Adapter continues when response JSON parsing fails."""
        adapter = DevtoAdapter(config={"tags": ["t1", "t2"]})

        bad_resp = MagicMock()
        bad_resp.json.side_effect = ValueError("Invalid JSON")

        good_resp = MagicMock()
        good_resp.json.return_value = [MOCK_DEVTO_ARTICLES[0]]
        good_resp.status_code = 200

        with patch(
            "max.sources.devto.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[bad_resp, good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1


# ── HTTP Client Integration Tests ────────────────────────────────────


class TestDevtoAdapterHttpClient:
    @pytest.mark.asyncio
    async def test_uses_async_client_with_timeout(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        client_timeout = None

        class MockAsyncClient:
            def __init__(self, **kwargs):
                nonlocal client_timeout
                client_timeout = kwargs.get("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("max.sources.devto.httpx.AsyncClient", MockAsyncClient):
            with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
                mock_resp = MagicMock()
                mock_resp.json.return_value = []
                mock_fetch.return_value = mock_resp
                await adapter.fetch(limit=10)

        assert client_timeout == 30

    @pytest.mark.asyncio
    async def test_sets_accept_json_header(self) -> None:
        adapter = DevtoAdapter(config={"tags": ["test"]})

        client_headers = None

        class MockAsyncClient:
            def __init__(self, **kwargs):
                nonlocal client_headers
                client_headers = kwargs.get("headers")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("max.sources.devto.httpx.AsyncClient", MockAsyncClient):
            with patch("max.sources.devto.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
                mock_resp = MagicMock()
                mock_resp.json.return_value = []
                mock_fetch.return_value = mock_resp
                await adapter.fetch(limit=10)

        assert client_headers is not None
        assert client_headers.get("Accept") == "application/json"
