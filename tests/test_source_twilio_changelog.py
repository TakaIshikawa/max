from __future__ import annotations

import pytest

from max.sources.registry import get_adapter, reload_registry
from max.sources.twilio_changelog import TwilioChangelogAdapter


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


def test_twilio_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert get_adapter("twilio_changelog").name == "twilio_changelog"
