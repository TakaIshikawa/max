from __future__ import annotations

import pytest

from max.sources.registry import get_adapter, reload_registry
from max.sources.stripe_changelog import StripeChangelogAdapter


@pytest.mark.asyncio
async def test_stripe_changelog_config_entries_return_signals_and_respect_limit() -> None:
    adapter = StripeChangelogAdapter(config={"entries": [{"title": "Payment links update", "url": "https://stripe.com/changelog/a", "published_at": "2026-05-01T00:00:00Z", "category": "payments"}, {"title": "API update", "url": "https://stripe.com/changelog/b"}]})

    signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].source_adapter == "stripe_changelog"
    assert signals[0].title == "Payment links update"
    assert signals[0].metadata["category"] == "payments"


def test_stripe_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    adapter = get_adapter("stripe_changelog")

    assert adapter.name == "stripe_changelog"
