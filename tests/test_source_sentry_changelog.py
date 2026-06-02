from __future__ import annotations

import pytest

from max.sources.registry import get_adapter, reload_registry
from max.sources.sentry_changelog import SentryChangelogAdapter


@pytest.mark.asyncio
async def test_sentry_changelog_preserves_platform_product_tags() -> None:
    signals = await SentryChangelogAdapter({"entries": [
        {"title": "Replay for mobile", "url": "https://sentry.example/changelog/replay", "platform": "ios", "product": "Session Replay", "tags": ["mobile"]},
    ]}).fetch()

    assert signals[0].source_adapter == "sentry_changelog"
    assert signals[0].metadata["platform"] == "ios"
    assert signals[0].metadata["product"] == "Session Replay"
    assert signals[0].metadata["tags"] == ["mobile"]


def test_sentry_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert get_adapter("sentry_changelog").name == "sentry_changelog"
