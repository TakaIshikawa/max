"""Tests for RSS/Atom feed import adapter — blog aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.rss_adapter import (
    RSSAdapter,
    _strip_html,
    parse_feed,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Tech Blog</title>
    <link>https://example.com</link>
    <item>
      <title>Understanding MCP Servers</title>
      <link>https://example.com/mcp-servers</link>
      <description>&lt;p&gt;A guide to Model Context Protocol.&lt;/p&gt;</description>
      <author>alice@example.com</author>
      <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Building AI Agents</title>
      <link>https://example.com/ai-agents</link>
      <description>How to build effective AI agents</description>
      <pubDate>Tue, 02 Jan 2024 14:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

SAMPLE_ATOM = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Dev Updates</title>
  <entry>
    <title>Rust in Production</title>
    <link rel="alternate" href="https://example.com/rust-prod"/>
    <summary>Lessons from running Rust in production.</summary>
    <author><name>Bob</name></author>
    <published>2024-01-15T10:00:00Z</published>
  </entry>
  <entry>
    <title>TypeScript Tips</title>
    <link rel="alternate" href="https://example.com/ts-tips"/>
    <content type="html">&lt;p&gt;Advanced TypeScript patterns.&lt;/p&gt;</content>
    <updated>2024-01-20T08:00:00Z</updated>
  </entry>
</feed>"""


def _mock_response(text: str, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_strip_html() -> None:
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_empty() -> None:
    assert _strip_html("") == ""


# ── Feed parsing tests ───────────────────────────────────────────────


def test_parse_rss_feed() -> None:
    entries = parse_feed(SAMPLE_RSS)
    assert len(entries) == 2
    assert entries[0]["title"] == "Understanding MCP Servers"
    assert entries[0]["link"] == "https://example.com/mcp-servers"
    assert entries[0]["author"] == "alice@example.com"
    assert entries[0]["published_at"] is not None
    assert entries[0]["feed_title"] == "Tech Blog"


def test_parse_atom_feed() -> None:
    entries = parse_feed(SAMPLE_ATOM)
    assert len(entries) == 2
    assert entries[0]["title"] == "Rust in Production"
    assert entries[0]["link"] == "https://example.com/rust-prod"
    assert entries[0]["author"] == "Bob"
    assert entries[0]["published_at"] is not None
    assert entries[0]["feed_title"] == "Dev Updates"


def test_parse_atom_content_fallback() -> None:
    entries = parse_feed(SAMPLE_ATOM)
    # Second entry has content but no summary
    assert "TypeScript" in entries[1]["summary"] or entries[1]["summary"] != ""


def test_parse_invalid_xml() -> None:
    entries = parse_feed("not xml")
    assert entries == []


def test_parse_unknown_format() -> None:
    entries = parse_feed("<?xml version='1.0'?><unknown/>")
    assert entries == []


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = RSSAdapter()
    assert adapter.name == "rss_import"


def test_adapter_source_type() -> None:
    adapter = RSSAdapter()
    assert adapter.source_type == SignalSourceType.ARTICLE.value


def test_adapter_default_feeds() -> None:
    adapter = RSSAdapter()
    assert adapter.feeds == []


def test_adapter_custom_feeds() -> None:
    adapter = RSSAdapter(config={"feeds": ["https://example.com/feed.xml"]})
    assert adapter.feeds == ["https://example.com/feed.xml"]


# ── Fetch tests with mocked HTTP ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_rss_feed() -> None:
    adapter = RSSAdapter(config={"feeds": ["https://example.com/rss"]})

    with patch(
        "max.imports.rss_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(SAMPLE_RSS)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "Understanding MCP Servers"
    assert sig.source_adapter == "rss_import"
    assert sig.source_type == SignalSourceType.ARTICLE
    assert sig.url == "https://example.com/mcp-servers"
    assert "rss" in sig.tags
    assert sig.metadata["feed_url"] == "https://example.com/rss"


@pytest.mark.asyncio
async def test_fetch_atom_feed() -> None:
    adapter = RSSAdapter(config={"feeds": ["https://example.com/atom"]})

    with patch(
        "max.imports.rss_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(SAMPLE_ATOM)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert signals[0].title == "Rust in Production"
    assert signals[0].author == "Bob"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = RSSAdapter(config={"feeds": ["https://example.com/rss"]})

    with patch(
        "max.imports.rss_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(SAMPLE_RSS)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates_by_link() -> None:
    adapter = RSSAdapter(config={
        "feeds": ["https://example.com/rss", "https://example.com/rss2"],
    })

    with patch(
        "max.imports.rss_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(SAMPLE_RSS)
        signals = await adapter.fetch(limit=10)

    # Same content from two feeds should deduplicate
    assert len(signals) == 2


@pytest.mark.asyncio
async def test_fetch_handles_error() -> None:
    adapter = RSSAdapter(config={"feeds": ["https://example.com/rss"]})

    with patch(
        "max.imports.rss_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("Network error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_feeds() -> None:
    adapter = RSSAdapter()
    signals = await adapter.fetch(limit=10)
    assert signals == []
