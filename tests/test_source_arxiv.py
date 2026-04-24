"""Comprehensive tests for ArXiv source adapter."""

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
from max.sources.arxiv import (
    ArxivAdapter,
    _extract_arxiv_id,
    _extract_tags,
    _normalize_whitespace,
    _parse_datetime,
    _parse_entries,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_ARXIV_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2404.12345v1</id>
    <title>ReAct Agent: Synergizing Reasoning and Acting in
      Language Models</title>
    <summary>We present a novel framework for building LLM agents
      that combines reasoning traces with tool-use actions.</summary>
    <published>2026-04-10T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="cs.AI" />
    <category term="cs.AI" />
    <category term="cs.CL" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2404.67890v1</id>
    <title>Embedding Models for Code Retrieval</title>
    <summary>A benchmark study of embedding approaches for code search.</summary>
    <published>2026-04-11T12:00:00Z</published>
    <author><name>Charlie Brown</name></author>
    <arxiv:primary_category term="cs.SE" />
    <category term="cs.SE" />
    <category term="cs.IR" />
  </entry>
</feed>
"""

MOCK_ARXIV_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>
"""

MOCK_ARXIV_SINGLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2404.99999v1</id>
    <title>Transformer Attention Mechanisms Survey</title>
    <summary>A comprehensive survey of attention in transformers.</summary>
    <published>2026-04-15T08:00:00Z</published>
    <author><name>Dana Researcher</name></author>
    <arxiv:primary_category term="cs.AI" />
    <category term="cs.AI" />
  </entry>
</feed>
"""

MOCK_ARXIV_NO_AUTHOR = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2404.11111v1</id>
    <title>Orphan Paper</title>
    <summary>A paper with no author elements.</summary>
    <published>2026-04-14T00:00:00Z</published>
    <arxiv:primary_category term="cs.AI" />
    <category term="cs.AI" />
  </entry>
</feed>
"""

MOCK_ARXIV_MISSING_TITLE = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2404.00001v1</id>
    <summary>Entry without a title element.</summary>
    <published>2026-04-14T00:00:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2404.00002v1</id>
    <title>Valid Entry</title>
    <summary>This one has a title.</summary>
    <published>2026-04-14T00:00:00Z</published>
  </entry>
</feed>
"""


# ── Unit Tests: _normalize_whitespace ────────────────────────────────


class TestNormalizeWhitespace:
    def test_collapses_newlines(self) -> None:
        assert _normalize_whitespace("hello\n  world") == "hello world"

    def test_strips_edges(self) -> None:
        assert _normalize_whitespace("  padded  ") == "padded"

    def test_collapses_tabs_and_mixed(self) -> None:
        assert _normalize_whitespace("a\t\n  b\n\tc") == "a b c"

    def test_empty_string(self) -> None:
        assert _normalize_whitespace("") == ""

    def test_single_word(self) -> None:
        assert _normalize_whitespace("hello") == "hello"


# ── Unit Tests: _extract_arxiv_id ────────────────────────────────────


class TestExtractArxivId:
    def test_from_url(self) -> None:
        assert _extract_arxiv_id("http://arxiv.org/abs/2404.12345v1") == "2404.12345v1"

    def test_trailing_slash(self) -> None:
        assert _extract_arxiv_id("http://arxiv.org/abs/2404.12345v1/") == "2404.12345v1"

    def test_bare_id(self) -> None:
        assert _extract_arxiv_id("2404.12345v1") == "2404.12345v1"


# ── Unit Tests: _extract_tags ────────────────────────────────────────


class TestExtractTags:
    def test_includes_categories(self) -> None:
        tags = _extract_tags("some title", ["cs.AI", "cs.CL"])
        assert "cs.ai" in tags
        assert "cs.cl" in tags

    def test_extracts_keywords(self) -> None:
        tags = _extract_tags("A new agent framework with tool use", [])
        assert "agent" in tags
        assert "tool-use" in tags

    def test_always_includes_arxiv(self) -> None:
        tags = _extract_tags("title", [])
        assert "arxiv" in tags

    def test_limits_to_10(self) -> None:
        many_cats = [f"cs.{chr(65 + i)}{chr(65 + i)}" for i in range(12)]
        tags = _extract_tags("agent llm rag embedding transformer", many_cats)
        assert len(tags) <= 10

    def test_lowercases_categories(self) -> None:
        tags = _extract_tags("title", ["CS.AI"])
        assert "cs.ai" in tags

    def test_keyword_llm(self) -> None:
        tags = _extract_tags("Fine-tuning LLM for code", [])
        assert "llm" in tags

    def test_keyword_language_model(self) -> None:
        tags = _extract_tags("Large language model pre-training", [])
        assert "llm" in tags

    def test_keyword_benchmark(self) -> None:
        tags = _extract_tags("A new benchmark for reasoning", [])
        assert "benchmark" in tags


# ── Unit Tests: _parse_datetime ──────────────────────────────────────


class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        dt = _parse_datetime("2026-04-10T00:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4

    def test_iso_with_offset(self) -> None:
        dt = _parse_datetime("2026-04-10T12:00:00+05:30")
        assert dt is not None
        assert dt.year == 2026

    def test_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None

    def test_empty(self) -> None:
        assert _parse_datetime("") is None


# ── Unit Tests: _parse_entries ───────────────────────────────────────


class TestParseEntries:
    def test_parses_two_entries(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_XML)
        assert len(entries) == 2

    def test_first_entry_fields(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_XML)
        e = entries[0]
        assert "ReAct Agent" in e["title"]
        assert "novel framework" in e["summary"]
        assert e["id"] == "http://arxiv.org/abs/2404.12345v1"
        assert e["authors"] == ["Alice Smith", "Bob Jones"]
        assert "cs.AI" in e["categories"]
        assert "cs.CL" in e["categories"]

    def test_whitespace_normalized_in_title(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_XML)
        assert "\n" not in entries[0]["title"]

    def test_whitespace_normalized_in_summary(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_XML)
        assert "\n" not in entries[0]["summary"]

    def test_empty_feed(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_EMPTY)
        assert entries == []

    def test_invalid_xml(self) -> None:
        entries = _parse_entries("not valid xml")
        assert entries == []

    def test_empty_input(self) -> None:
        entries = _parse_entries("")
        assert entries == []

    def test_skips_entries_without_title(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_MISSING_TITLE)
        assert len(entries) == 1
        assert entries[0]["title"] == "Valid Entry"

    def test_entry_with_no_authors(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_NO_AUTHOR)
        assert len(entries) == 1
        assert entries[0]["authors"] == []

    def test_primary_category_first(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_XML)
        assert entries[0]["categories"][0] == "cs.AI"


# ── Adapter Property Tests ───────────────────────────────────────────


class TestArxivAdapterProperties:
    def test_name(self) -> None:
        assert ArxivAdapter().name == "arxiv"

    def test_source_type(self) -> None:
        assert ArxivAdapter().source_type == SignalSourceType.SURVEY.value

    def test_config_defaults(self) -> None:
        a = ArxivAdapter()
        assert "cs.AI" in a.categories
        assert len(a.queries) > 0

    def test_config_overrides_categories(self) -> None:
        a = ArxivAdapter(config={"categories": ["stat.ML", "cs.LG"]})
        assert a.categories == ["stat.ML", "cs.LG"]

    def test_config_overrides_queries(self) -> None:
        a = ArxivAdapter(config={"queries": ["ti:custom"]})
        assert a.queries == ["ti:custom"]

    def test_inherits_from_source_adapter(self) -> None:
        assert isinstance(ArxivAdapter(), SourceAdapter)

    def test_accepts_config(self) -> None:
        config = {"categories": ["cs.AI"], "custom": "val"}
        a = ArxivAdapter(config=config)
        assert a._config == config

    def test_no_config(self) -> None:
        a = ArxivAdapter()
        assert a._config == {}


# ── Adapter Fetch Tests ──────────────────────────────────────────────


class TestArxivAdapterFetch:
    @pytest.mark.asyncio
    async def test_fetch_parses_papers(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["ti:agent"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 2
        assert signals[0].source_adapter == "arxiv"
        assert signals[0].source_type == SignalSourceType.SURVEY
        assert "ReAct Agent" in signals[0].title
        assert signals[0].url == "http://arxiv.org/abs/2404.12345v1"
        assert signals[0].author == "Alice Smith"
        assert signals[0].credibility == 0.6
        assert signals[0].metadata["arxiv_id"] == "2404.12345v1"
        assert signals[0].metadata["search_query"] == "ti:agent"

    @pytest.mark.asyncio
    async def test_fetch_second_entry_fields(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.SE"],
            "queries": ["ti:embedding"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals[1].title == "Embedding Models for Code Retrieval"
        assert signals[1].author == "Charlie Brown"
        assert signals[1].metadata["arxiv_id"] == "2404.67890v1"
        assert "cs.SE" in signals[1].metadata["categories"]

    @pytest.mark.asyncio
    async def test_fetch_no_author_entry(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["ti:orphan"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_NO_AUTHOR
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].author is None

    @pytest.mark.asyncio
    async def test_fetch_content_truncated_to_1000(self) -> None:
        long_summary = "x" * 2000
        xml = f"""\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2404.99999v1</id>
    <title>Long Paper</title>
    <summary>{long_summary}</summary>
    <published>2026-04-10T00:00:00Z</published>
    <arxiv:primary_category term="cs.AI" />
    <category term="cs.AI" />
  </entry>
</feed>
"""
        adapter = ArxivAdapter(config={"categories": ["cs.AI"], "queries": ["test"]})
        mock_resp = MagicMock()
        mock_resp.text = xml
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals[0].content) <= 1000

    @pytest.mark.asyncio
    async def test_fetch_deduplicates_across_queries(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["query1", "query2"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        # Same XML returned for both queries, dedup by arxiv_id
        assert len(signals) == 2

    @pytest.mark.asyncio
    async def test_fetch_respects_limit(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["test"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_empty_feed(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["no results"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_EMPTY
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_metadata_fields(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["test"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        meta = signals[0].metadata
        assert "arxiv_id" in meta
        assert "categories" in meta
        assert "authors" in meta
        assert "primary_category" in meta
        assert "search_query" in meta
        assert meta["primary_category"] == "cs.AI"
        assert meta["authors"] == ["Alice Smith", "Bob Jones"]

    @pytest.mark.asyncio
    async def test_fetch_published_at_parsed(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["test"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        assert signals[0].published_at is not None
        assert signals[0].published_at.year == 2026
        assert signals[0].published_at.month == 4
        assert signals[0].published_at.day == 10

    @pytest.mark.asyncio
    async def test_fetch_tags_include_categories_and_keywords(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["test"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_XML
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=1)

        tags = signals[0].tags
        assert "arxiv" in tags
        assert "cs.ai" in tags
        assert "agent" in tags

    @pytest.mark.asyncio
    async def test_fetch_calls_api_with_correct_params(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI", "cs.CL"],
            "queries": ["ti:test"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_EMPTY
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp) as mock_fetch:
            await adapter.fetch(limit=10)

        call_kwargs = mock_fetch.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params", {})
        assert "cat:cs.AI" in params["search_query"]
        assert "cat:cs.CL" in params["search_query"]
        assert "ti:test" in params["search_query"]
        assert params["sortBy"] == "submittedDate"
        assert params["sortOrder"] == "descending"
        assert call_kwargs.kwargs.get("adapter_name") == "arxiv"

    @pytest.mark.asyncio
    async def test_fetch_sleeps_between_queries(self) -> None:
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["query1", "query2"],
        })

        mock_resp = MagicMock()
        mock_resp.text = MOCK_ARXIV_SINGLE
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await adapter.fetch(limit=10)

        mock_sleep.assert_called_once_with(3)


# ── Error Handling Tests ─────────────────────────────────────────────


class TestArxivAdapterErrors:
    @pytest.mark.asyncio
    async def test_fetch_continues_on_query_error(self) -> None:
        """Adapter logs warning and continues when a query fails."""
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["bad_query", "good_query"],
        })

        mock_good_resp = MagicMock()
        mock_good_resp.text = MOCK_ARXIV_SINGLE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.arxiv.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterFetchError("arxiv", 500, "url"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_rate_limit(self) -> None:
        """Adapter continues with next query when rate limited."""
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["q1", "q2"],
        })

        mock_good_resp = MagicMock()
        mock_good_resp.text = MOCK_ARXIV_SINGLE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.arxiv.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterRateLimitError("arxiv", "url"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_circuit_open(self) -> None:
        """Adapter continues with next query when circuit is open."""
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["q1", "q2"],
        })

        mock_good_resp = MagicMock()
        mock_good_resp.text = MOCK_ARXIV_SINGLE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.arxiv.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[AdapterCircuitOpenError("arxiv", retry_after=300.0), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_continues_on_timeout(self) -> None:
        """Adapter continues with next query on network timeout."""
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["q1", "q2"],
        })

        mock_good_resp = MagicMock()
        mock_good_resp.text = MOCK_ARXIV_SINGLE
        mock_good_resp.status_code = 200

        with patch(
            "max.sources.arxiv.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[httpx.TimeoutException("timeout"), mock_good_resp],
        ):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                signals = await adapter.fetch(limit=10)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_all_queries_fail_returns_empty(self) -> None:
        """Adapter returns empty list when all queries fail."""
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["q1"],
        })

        with patch(
            "max.sources.arxiv.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=AdapterFetchError("arxiv", 503, "url"),
        ):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_handles_malformed_xml_response(self) -> None:
        """Adapter gracefully handles non-XML response text."""
        adapter = ArxivAdapter(config={
            "categories": ["cs.AI"],
            "queries": ["test"],
        })

        mock_resp = MagicMock()
        mock_resp.text = "<html>Error page</html>"
        mock_resp.status_code = 200

        with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals == []


# ── HTTP Client Integration Tests ────────────────────────────────────


class TestArxivAdapterHttpClient:
    @pytest.mark.asyncio
    async def test_uses_async_client_with_timeout(self) -> None:
        adapter = ArxivAdapter(config={"categories": ["cs.AI"], "queries": ["test"]})

        client_timeout = None

        class MockAsyncClient:
            def __init__(self, **kwargs):
                nonlocal client_timeout
                client_timeout = kwargs.get("timeout")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("max.sources.arxiv.httpx.AsyncClient", MockAsyncClient):
            with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
                mock_resp = MagicMock()
                mock_resp.text = MOCK_ARXIV_EMPTY
                mock_fetch.return_value = mock_resp
                await adapter.fetch(limit=10)

        assert client_timeout == 30

    @pytest.mark.asyncio
    async def test_sets_user_agent_header(self) -> None:
        adapter = ArxivAdapter(config={"categories": ["cs.AI"], "queries": ["test"]})

        client_headers = None

        class MockAsyncClient:
            def __init__(self, **kwargs):
                nonlocal client_headers
                client_headers = kwargs.get("headers")

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("max.sources.arxiv.httpx.AsyncClient", MockAsyncClient):
            with patch("max.sources.arxiv.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
                mock_resp = MagicMock()
                mock_resp.text = MOCK_ARXIV_EMPTY
                mock_fetch.return_value = mock_resp
                await adapter.fetch(limit=10)

        assert client_headers is not None
        assert "User-Agent" in client_headers
