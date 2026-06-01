from __future__ import annotations

import pytest

from max.sources.fly_io_changelog import FlyIoChangelogAdapter, parse_fly_io_changelog


def test_fly_io_changelog_parses_payload() -> None:
    signals = parse_fly_io_changelog([{"title": "Machines update", "url": "https://fly.io/changelog/a", "published_at": "2026-05-01T00:00:00Z", "summary": "New platform feature", "platform": "machines"}])
    assert signals[0].source_adapter == "fly_io_changelog"
    assert signals[0].metadata["platform"] == "machines"
    assert signals[0].published_at is not None


def test_fly_io_changelog_missing_optional_fields_and_stable_ids() -> None:
    payload = [{"title": "Update", "url": "https://fly.io/changelog/u"}]
    assert parse_fly_io_changelog(payload)[0].id == parse_fly_io_changelog(payload)[0].id


def test_fly_io_changelog_empty_or_malformed() -> None:
    assert parse_fly_io_changelog({}) == []
    assert parse_fly_io_changelog([{"title": "missing url"}]) == []


@pytest.mark.asyncio
async def test_fly_io_changelog_adapter_fetch_uses_config_payload() -> None:
    signals = await FlyIoChangelogAdapter(config={"entries": [{"title": "A", "url": "https://fly.io/a"}]}).fetch()
    assert len(signals) == 1
