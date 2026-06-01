from __future__ import annotations

import pytest

from max.sources.zapier_developer_changelog import ZapierDeveloperChangelogAdapter, parse_zapier_developer_changelog


def test_zapier_developer_changelog_entries_become_signals() -> None:
    signals = parse_zapier_developer_changelog([{"title": "CLI platform update", "url": "https://zapier.com/changelog/cli", "summary": "New API"}])
    assert signals[0].source_adapter == "zapier_developer_changelog"
    assert signals[0].content == "New API"


def test_zapier_developer_changelog_platform_app_metadata() -> None:
    signal = parse_zapier_developer_changelog([{"title": "App update", "url": "https://zapier.com/changelog/app", "platform": "developer", "app": "cli"}])[0]
    assert signal.metadata["platform"] == "developer"
    assert signal.metadata["app"] == "cli"


def test_zapier_developer_changelog_empty_and_stable_ids() -> None:
    payload = [{"title": "A", "url": "https://zapier/a"}]
    assert parse_zapier_developer_changelog([]) == []
    assert parse_zapier_developer_changelog(payload)[0].id == parse_zapier_developer_changelog(payload)[0].id


@pytest.mark.asyncio
async def test_zapier_developer_changelog_adapter_limit() -> None:
    signals = await ZapierDeveloperChangelogAdapter(config={"entries": [{"title": "A", "url": "https://z/a"}, {"title": "B", "url": "https://z/b"}]}).fetch(limit=1)
    assert len(signals) == 1
