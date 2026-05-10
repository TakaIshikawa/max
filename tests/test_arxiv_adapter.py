"""Tests for arXiv import adapter — research paper signal collection."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.arxiv_adapter import (
    ArxivAdapter,
    _extract_arxiv_id,
    _extract_tags,
    _normalize_whitespace,
    _parse_entries,
    _parse_datetime,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_ARXIV_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2405.12345v1</id>
    <title>Agent Tool Use in Large Language Models</title>
    <summary>We present a framework for LLM agent tool use.</summary>
    <published>2026-05-01T18:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <arxiv:primary_category term="cs.AI"/>
    <category term="cs.AI"/>
    <category term="cs.CL"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2405.67890v1</id>
    <title>Retrieval Augmented Generation for Code</title>
    <summary>RAG techniques applied to code generation benchmarks.</summary>
    <published>2026-05-02T12:00:00Z</published>
    <author><name>Carol Lee</name></author>
    <arxiv:primary_category term="cs.SE"/>
    <category term="cs.SE"/>
    <category term="cs.AI"/>
  </entry>
</feed>"""

MOCK_ARXIV_EMPTY = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>"""


def _mock_response(text: str, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_normalize_whitespace() -> None:
    assert _normalize_whitespace("  hello\n  world  ") == "hello world"


def test_extract_arxiv_id() -> None:
    assert _extract_arxiv_id("http://arxiv.org/abs/2405.12345v1") == "2405.12345v1"


def test_extract_arxiv_id_simple() -> None:
    assert _extract_arxiv_id("2405.12345") == "2405.12345"


def test_extract_tags_categories() -> None:
    tags = _extract_tags("Some title", ["cs.AI", "cs.CL"])
    assert "cs.ai" in tags
    assert "cs.cl" in tags
    assert "arxiv" in tags


def test_extract_tags_keywords() -> None:
    tags = _extract_tags("Agent Tool Use in LLM Systems", ["cs.AI"])
    assert "agent" in tags
    assert "tool-use" in tags
    assert "llm" in tags


def test_parse_datetime_valid() -> None:
    dt = _parse_datetime("2026-05-01T18:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2026


def test_parse_datetime_invalid() -> None:
    assert _parse_datetime("not-a-date") is None


def test_parse_datetime_empty() -> None:
    assert _parse_datetime("") is None


def test_parse_entries_valid_xml() -> None:
    entries = _parse_entries(MOCK_ARXIV_XML)
    assert len(entries) == 2
    assert entries[0]["title"] == "Agent Tool Use in Large Language Models"
    assert entries[0]["authors"] == ["Alice Smith", "Bob Jones"]
    assert "cs.AI" in entries[0]["categories"]
    assert entries[1]["title"] == "Retrieval Augmented Generation for Code"


def test_parse_entries_empty_feed() -> None:
    entries = _parse_entries(MOCK_ARXIV_EMPTY)
    assert entries == []


def test_parse_entries_invalid_xml() -> None:
    entries = _parse_entries("not xml at all")
    assert entries == []


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = ArxivAdapter()
    assert adapter.name == "arxiv_import"


def test_adapter_source_type() -> None:
    adapter = ArxivAdapter()
    assert adapter.source_type == SignalSourceType.SURVEY.value


def test_adapter_default_categories() -> None:
    adapter = ArxivAdapter()
    assert "cs.AI" in adapter.categories
    assert "cs.SE" in adapter.categories


def test_adapter_custom_categories() -> None:
    adapter = ArxivAdapter(config={"categories": ["cs.LG", "stat.ML"]})
    assert adapter.categories == ["cs.LG", "stat.ML"]


def test_adapter_default_queries() -> None:
    adapter = ArxivAdapter()
    assert len(adapter.queries) >= 2


def test_adapter_author_config() -> None:
    adapter = ArxivAdapter(config={"author": "Hinton"})
    assert adapter.author == "Hinton"


def test_adapter_author_default_none() -> None:
    adapter = ArxivAdapter()
    assert adapter.author is None


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_parses_papers() -> None:
    adapter = ArxivAdapter(config={"queries": ["ti:agent"]})

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_ARXIV_XML)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "Agent Tool Use in Large Language Models"
    assert sig.source_adapter == "arxiv_import"
    assert sig.source_type == SignalSourceType.SURVEY
    assert sig.url == "http://arxiv.org/abs/2405.12345v1"
    assert sig.author == "Alice Smith"
    assert sig.metadata["arxiv_id"] == "2405.12345v1"
    assert sig.metadata["categories"] == ["cs.AI", "cs.CL"]
    assert sig.metadata["authors"] == ["Alice Smith", "Bob Jones"]
    assert sig.published_at is not None
    assert sig.credibility == 0.6


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = ArxivAdapter(config={"queries": ["ti:agent"]})

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_ARXIV_XML)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    # Two queries returning same entries
    adapter = ArxivAdapter(config={"queries": ["ti:agent", "ti:tool"]})

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_ARXIV_XML)

        with patch("max.imports.arxiv_adapter.asyncio.sleep", new_callable=AsyncMock):
            signals = await adapter.fetch(limit=10)

    # Each entry appears only once despite two queries
    ids = [s.metadata["arxiv_id"] for s in signals]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = ArxivAdapter(config={"queries": ["ti:agent"]})

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_feed() -> None:
    adapter = ArxivAdapter(config={"queries": ["ti:agent"]})

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_ARXIV_EMPTY)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_with_author_filter() -> None:
    adapter = ArxivAdapter(config={"queries": ["ti:agent"], "author": "Hinton"})

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_ARXIV_XML)
        await adapter.fetch(limit=10)

    query = mock_fetch.call_args.kwargs["params"]["search_query"]
    assert "au:Hinton" in query


@pytest.mark.asyncio
async def test_build_query_includes_categories() -> None:
    adapter = ArxivAdapter(config={
        "queries": ["ti:agent"],
        "categories": ["cs.AI", "cs.SE"],
    })

    with patch(
        "max.imports.arxiv_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_ARXIV_XML)
        await adapter.fetch(limit=10)

    query = mock_fetch.call_args.kwargs["params"]["search_query"]
    assert "cat:cs.AI" in query
    assert "cat:cs.SE" in query
