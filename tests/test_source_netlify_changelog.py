from __future__ import annotations

import pytest

from max.sources import netlify_changelog as module
from max.sources.netlify_changelog import NetlifyChangelogAdapter, parse_netlify_changelog
from max.types.signal import SignalSourceType


RSS = """<rss><channel>
<item><title>Deploy previews improve</title><link>https://netlify.com/changelog/a</link><description>Preview rollout</description><pubDate>Mon, 01 Jun 2026 00:00:00 +0000</pubDate><category>deploys</category></item>
<item><title>Duplicate</title><link>https://netlify.com/changelog/a</link><category>deploys</category></item>
<item><title>Forms update</title><link>https://netlify.com/changelog/b</link><description>Forms routing</description><pubDate>2026-05-01T00:00:00Z</pubDate><category>forms</category></item>
</channel></rss>"""


def test_netlify_changelog_parses_rss_and_deduplicates_by_url() -> None:
    signals = parse_netlify_changelog(RSS, feed_url="https://example.test/rss")

    assert len(signals) == 2
    assert signals[0].source_adapter == "netlify_changelog"
    assert signals[0].source_type == SignalSourceType.NEWS
    assert signals[0].tags[:2] == ["netlify", "deploys"]
    assert signals[0].metadata["feed_url"] == "https://example.test/rss"
    assert signals[0].metadata["categories"] == ["deploys"]


@pytest.mark.asyncio
async def test_netlify_changelog_fetch_honors_limit_and_filters(monkeypatch) -> None:
    monkeypatch.setattr(module, "_now", lambda: module.datetime(2026, 6, 2, tzinfo=module.timezone.utc))
    adapter = NetlifyChangelogAdapter({"payload": RSS, "products": ["deploys"], "keywords": ["preview"], "max_age_days": 7})

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].title == "Deploy previews improve"


@pytest.mark.asyncio
async def test_netlify_changelog_malformed_feed_and_fetch_exceptions_return_empty(monkeypatch) -> None:
    assert parse_netlify_changelog("<rss>") == []

    async def fail(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(module, "_fetch_text", fail)
    assert await NetlifyChangelogAdapter({}).fetch() == []
