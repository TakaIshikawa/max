"""Tests for configured RSS/Atom source adapter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.rss_feed import RssFeedAdapter, _normalize_text, _parse_datetime, _parse_rss_entries
from max.types.signal import SignalSourceType


RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>RSS Article</title>
      <link>https://example.com/rss-article</link>
      <description><![CDATA[<p>Useful RSS summary&nbsp;here.</p>]]></description>
      <pubDate>Wed, 22 Apr 2026 10:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


ATOM_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom Article</title>
    <link href="https://example.com/atom-article" rel="alternate" />
    <summary>Atom summary</summary>
    <published>2026-04-22T11:30:00Z</published>
  </entry>
</feed>
"""


def test_normalize_text_strips_html_and_collapses_whitespace() -> None:
    assert _normalize_text("<p>Hello&nbsp; world</p>\n\nAgain") == "Hello world Again"


def test_parse_datetime_handles_rss_and_atom_dates() -> None:
    rss_dt = _parse_datetime("Wed, 22 Apr 2026 10:30:00 GMT")
    atom_dt = _parse_datetime("2026-04-22T11:30:00Z")

    assert rss_dt == datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc)
    assert atom_dt == datetime(2026, 4, 22, 11, 30, tzinfo=timezone.utc)
    assert _parse_datetime("not-a-date") is None


def test_parse_rss_entries_extracts_rss_items() -> None:
    entries = _parse_rss_entries(RSS_XML, "https://example.com/feed.xml")

    assert len(entries) == 1
    assert entries[0]["title"] == "RSS Article"
    assert entries[0]["url"] == "https://example.com/rss-article"
    assert entries[0]["content"] == "Useful RSS summary here."
    assert entries[0]["published_at"] == datetime(2026, 4, 22, 10, 30, tzinfo=timezone.utc)


def test_parse_rss_entries_extracts_atom_entries() -> None:
    entries = _parse_rss_entries(ATOM_XML, "https://example.com/atom.xml")

    assert len(entries) == 1
    assert entries[0]["title"] == "Atom Article"
    assert entries[0]["url"] == "https://example.com/atom-article"
    assert entries[0]["content"] == "Atom summary"


class TestRssFeedAdapter:
    def test_name_and_source_type(self) -> None:
        adapter = RssFeedAdapter()

        assert adapter.name == "rss_feed"
        assert adapter.source_type == SignalSourceType.ARTICLE.value

    def test_config_properties(self) -> None:
        adapter = RssFeedAdapter(config={
            "feeds": ["https://example.com/feed.xml"],
            "tags": ["ai", "research"],
            "max_age_days": 7,
        })

        assert adapter.feeds == ["https://example.com/feed.xml"]
        assert adapter.tags == ["ai", "research"]
        assert adapter.max_age_days == 7

    @pytest.mark.asyncio
    async def test_fetch_converts_entries_to_signals(self) -> None:
        adapter = RssFeedAdapter(config={
            "feeds": ["https://example.com/feed.xml"],
            "tags": ["ai", "research"],
        })
        mock_resp = MagicMock()
        mock_resp.text = RSS_XML
        mock_resp.status_code = 200

        with patch("max.sources.rss_feed.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        signal = signals[0]
        assert signal.source_type == SignalSourceType.ARTICLE
        assert signal.source_adapter == "rss_feed"
        assert signal.title == "RSS Article"
        assert signal.content == "Useful RSS summary here."
        assert signal.url == "https://example.com/rss-article"
        assert signal.tags == ["ai", "research"]
        assert signal.metadata["feed_url"] == "https://example.com/feed.xml"

    @pytest.mark.asyncio
    async def test_fetch_respects_limit_and_deduplicates_urls(self) -> None:
        adapter = RssFeedAdapter(config={"feeds": ["https://example.com/feed.xml"]})
        duplicate_item = """\
    <item>
      <title>RSS Article Duplicate</title>
      <link>https://example.com/rss-article</link>
      <description>Duplicate summary.</description>
      <pubDate>Wed, 22 Apr 2026 10:31:00 GMT</pubDate>
    </item>
"""
        xml = RSS_XML.replace("</channel>", f"{duplicate_item}</channel>")
        mock_resp = MagicMock()
        mock_resp.text = xml
        mock_resp.status_code = 200

        with patch("max.sources.rss_feed.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=5)

        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_fetch_filters_entries_older_than_max_age(self) -> None:
        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        xml = RSS_XML.replace("Wed, 22 Apr 2026 10:30:00 GMT", old_date)
        adapter = RssFeedAdapter(config={
            "feeds": ["https://example.com/feed.xml"],
            "max_age_days": 7,
        })
        mock_resp = MagicMock()
        mock_resp.text = xml
        mock_resp.status_code = 200

        with patch("max.sources.rss_feed.fetch_with_retry", new_callable=AsyncMock, return_value=mock_resp):
            signals = await adapter.fetch(limit=10)

        assert signals == []

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_without_configured_feeds(self) -> None:
        assert await RssFeedAdapter().fetch(limit=10) == []
