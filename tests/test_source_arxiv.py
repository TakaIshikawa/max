"""Tests for ArXiv source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


# ── Unit Tests ────────────────────────────────────────────────────────


class TestNormalizeWhitespace:
    def test_collapses_newlines(self) -> None:
        assert _normalize_whitespace("hello\n  world") == "hello world"

    def test_strips_edges(self) -> None:
        assert _normalize_whitespace("  padded  ") == "padded"


class TestExtractArxivId:
    def test_from_url(self) -> None:
        assert _extract_arxiv_id("http://arxiv.org/abs/2404.12345v1") == "2404.12345v1"

    def test_trailing_slash(self) -> None:
        assert _extract_arxiv_id("http://arxiv.org/abs/2404.12345v1/") == "2404.12345v1"


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


class TestParseDatetime:
    def test_iso_with_z(self) -> None:
        dt = _parse_datetime("2026-04-10T00:00:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 4

    def test_invalid(self) -> None:
        assert _parse_datetime("not-a-date") is None

    def test_empty(self) -> None:
        assert _parse_datetime("") is None


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
        # The title has embedded newlines in the XML — should be normalized
        assert "\n" not in entries[0]["title"]

    def test_empty_feed(self) -> None:
        entries = _parse_entries(MOCK_ARXIV_EMPTY)
        assert entries == []

    def test_invalid_xml(self) -> None:
        entries = _parse_entries("not valid xml")
        assert entries == []


# ── Adapter Tests ────────────────────────────────────────────────────


class TestArxivAdapter:
    def test_name(self) -> None:
        assert ArxivAdapter().name == "arxiv"

    def test_source_type(self) -> None:
        assert ArxivAdapter().source_type == SignalSourceType.SURVEY.value

    def test_config_defaults(self) -> None:
        a = ArxivAdapter()
        assert "cs.AI" in a.categories
        assert len(a.queries) > 0

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
        assert "ReAct Agent" in signals[0].title
        assert signals[0].url == "http://arxiv.org/abs/2404.12345v1"
        assert signals[0].author == "Alice Smith"
        assert signals[0].credibility == 0.6
        assert signals[0].metadata["arxiv_id"] == "2404.12345v1"

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
