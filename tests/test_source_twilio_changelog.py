from __future__ import annotations

import pytest

from max.sources import twilio_changelog as module
from max.sources.registry import get_adapter, reload_registry
from max.sources.twilio_changelog import TwilioChangelogAdapter, parse_twilio_changelog
from max.types.signal import SignalSourceType


RSS = """<rss><channel>
<item><title>Messaging API release</title><link>https://twilio.com/changelog/a</link><description>SMS routing</description><pubDate>2026-06-01T00:00:00Z</pubDate><category>messaging</category></item>
<item><title>Voice API release</title><link>https://twilio.com/changelog/b</link><description>Call update</description><pubDate>2026-05-01T00:00:00Z</pubDate><category>voice</category></item>
<item><title>Duplicate</title><link>https://twilio.com/changelog/a</link></item>
</channel></rss>"""


def test_twilio_changelog_adapter_identity() -> None:
    adapter = TwilioChangelogAdapter({"payload": RSS})

    assert adapter.name == "twilio_changelog"
    assert adapter.source_type == SignalSourceType.ROADMAP.value


@pytest.mark.asyncio
async def test_twilio_changelog_fetch_deduplicates_and_respects_limit() -> None:
    signals = await TwilioChangelogAdapter({"payload": RSS}).fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].source_adapter == "twilio_changelog"
    assert signals[0].source_type == SignalSourceType.ROADMAP
    assert "twilio" in signals[0].tags


def test_twilio_changelog_filters_products_and_keywords() -> None:
    signals = parse_twilio_changelog(RSS, products=["messaging"], keywords=["sms"])

    assert [signal.title for signal in signals] == ["Messaging API release"]


@pytest.mark.asyncio
async def test_twilio_changelog_entries_become_signals_and_skip_malformed() -> None:
    signals = await TwilioChangelogAdapter({"entries": [
        {"title": "Voice Insights update", "url": "https://twilio.example/changelog/1", "product": "Voice", "category": "feature"},
        {"title": "Missing URL"},
        {"url": "https://twilio.example/changelog/missing-title"},
    ]}).fetch()

    assert len(signals) == 1
    assert signals[0].source_adapter == "twilio_changelog"
    assert signals[0].metadata["products"] == ["Voice"]
    assert signals[0].metadata["category"] == "feature"


@pytest.mark.asyncio
async def test_twilio_changelog_fetch_and_parse_failures_return_empty(monkeypatch) -> None:
    assert parse_twilio_changelog("<rss>") == []

    async def fail(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(module, "_entries_from_config_or_feed", fail)
    assert await TwilioChangelogAdapter({}).fetch() == []


def test_twilio_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert get_adapter("twilio_changelog").name == "twilio_changelog"
