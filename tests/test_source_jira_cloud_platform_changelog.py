from __future__ import annotations

import pytest

from max.sources.jira_cloud_platform_changelog import JiraCloudPlatformChangelogAdapter
from max.sources.registry import get_adapter, reload_registry


@pytest.mark.asyncio
async def test_jira_changelog_config_entries_return_signals_and_mark_deprecations() -> None:
    adapter = JiraCloudPlatformChangelogAdapter(config={"entries": [{"title": "Deprecated endpoint", "url": "https://developer.atlassian.com/cloud/jira/platform/changelog/#a", "published_at": "2026-05-01T00:00:00Z", "product_area": "issue-search", "deprecation": True}]})

    signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert signals[0].source_adapter == "jira_cloud_platform_changelog"
    assert signals[0].metadata["product_area"] == "issue-search"
    assert signals[0].metadata["deprecation"] is True


def test_jira_changelog_registry_instantiates_adapter() -> None:
    reload_registry()
    adapter = get_adapter("jira_cloud_platform_changelog")

    assert adapter.name == "jira_cloud_platform_changelog"
