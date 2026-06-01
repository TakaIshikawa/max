from __future__ import annotations

from max.sources.railway_changelog import parse_railway_changelog


def test_railway_changelog_normal_entries_and_metadata() -> None:
    signals = parse_railway_changelog([{"title": "Deployments", "url": "https://railway.com/changelog/a", "category": "deploy", "tags": ["platform"]}])
    assert signals[0].source_adapter == "railway_changelog"
    assert signals[0].metadata["category"] == "deploy"


def test_railway_changelog_tolerates_missing_date_category_author() -> None:
    signal = parse_railway_changelog([{"title": "A", "url": "https://railway.com/a"}])[0]
    assert signal.published_at is None
    assert signal.title == "A"


def test_railway_changelog_deterministic_ids_and_empty_payloads() -> None:
    payload = [{"title": "A", "url": "https://railway.com/a"}]
    assert parse_railway_changelog(payload)[0].id == parse_railway_changelog(payload)[0].id
    assert parse_railway_changelog(None) == []
