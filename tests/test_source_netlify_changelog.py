from __future__ import annotations

import pytest

from max.sources.netlify_changelog import NetlifyChangelogAdapter
from max.sources.registry import get_adapter, reload_registry


@pytest.mark.asyncio
async def test_netlify_changelog_dedupes_duplicate_urls() -> None:
    signals = await NetlifyChangelogAdapter({"entries": [
        {"title": "Build cache update", "url": "https://netlify.example/changelog/cache", "product_area": "Builds", "impact": "performance"},
        {"title": "Duplicate", "url": "https://netlify.example/changelog/cache"},
    ]}).fetch()

    assert len(signals) == 1
    assert signals[0].source_adapter == "netlify_changelog"
    assert signals[0].metadata["product_area"] == "Builds"
    assert signals[0].metadata["impact"] == "performance"


def test_netlify_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    assert get_adapter("netlify_changelog").name == "netlify_changelog"
