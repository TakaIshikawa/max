from __future__ import annotations

import pytest

from max.sources.linear_changelog import LinearChangelogAdapter, parse_linear_changelog


def test_linear_changelog_entries_become_signals() -> None:
    signals = parse_linear_changelog([{"title": "Triage updates", "url": "https://linear.app/changelog/triage", "summary": "Better triage", "published_at": "2026-05-01T00:00:00Z"}])
    assert signals[0].source_adapter == "linear_changelog"
    assert signals[0].content == "Better triage"


def test_linear_changelog_feature_category_metadata() -> None:
    signal = parse_linear_changelog([{"title": "Cycles", "url": "https://linear.app/changelog/cycles", "feature_category": "planning"}])[0]
    assert signal.metadata["feature_category"] == "planning"


def test_linear_changelog_stable_ids_and_empty_payload() -> None:
    payload = [{"title": "A", "url": "https://linear/a"}]
    assert parse_linear_changelog(payload)[0].id == parse_linear_changelog(payload)[0].id
    assert parse_linear_changelog([]) == []


@pytest.mark.asyncio
async def test_linear_changelog_adapter_limit() -> None:
    signals = await LinearChangelogAdapter(config={"entries": [{"title": "A", "url": "https://l/a"}, {"title": "B", "url": "https://l/b"}]}).fetch(limit=1)
    assert len(signals) == 1
