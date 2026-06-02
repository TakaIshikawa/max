from __future__ import annotations

from datetime import datetime, timezone

import pytest

from max.sources import google_workspace_developer_changelog as module
from max.sources.google_workspace_developer_changelog import (
    GoogleWorkspaceDeveloperChangelogAdapter,
    parse_google_workspace_developer_changelog,
)
from max.types.signal import SignalSourceType


RSS = """<rss><channel>
<item><title>Google Drive API update</title><link>https://developers.google.com/workspace/a</link><description>Drive labels</description><pubDate>2026-06-01T00:00:00Z</pubDate><category>drive</category></item>
<item><title>Google Chat API update</title><link>https://developers.google.com/workspace/b</link><description>Chat spaces</description><pubDate>2026-05-01T00:00:00Z</pubDate><category>chat</category></item>
<item><title>Duplicate</title><link>https://developers.google.com/workspace/a</link></item>
</channel></rss>"""


def test_google_workspace_developer_changelog_parses_entries_to_news_signals() -> None:
    signals = parse_google_workspace_developer_changelog(RSS)

    assert len(signals) == 2
    assert signals[0].source_adapter == "google_workspace_developer_changelog"
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].published_at.tzinfo is not None
    assert "google-workspace" in signals[0].tags


@pytest.mark.asyncio
async def test_google_workspace_developer_changelog_filters_without_optional_fields(monkeypatch) -> None:
    monkeypatch.setattr("max.sources.netlify_changelog._now", lambda: datetime(2026, 6, 2, tzinfo=timezone.utc))
    adapter = GoogleWorkspaceDeveloperChangelogAdapter({"payload": RSS, "products": ["drive"], "keywords": ["labels"], "max_age_days": 7})

    signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["Google Drive API update"]


@pytest.mark.asyncio
async def test_google_workspace_developer_changelog_invalid_xml_and_fetch_failures(monkeypatch) -> None:
    assert parse_google_workspace_developer_changelog("<rss>") == []

    async def fail(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(module, "_fetch_text", fail)
    assert await GoogleWorkspaceDeveloperChangelogAdapter({}).fetch() == []
