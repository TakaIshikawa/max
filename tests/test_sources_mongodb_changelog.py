from __future__ import annotations

from max.sources.mongodb_changelog import parse_mongodb_changelog


def test_mongodb_changelog_preserves_version_and_product() -> None:
    signal = parse_mongodb_changelog([{"title": "MongoDB 8.0", "url": "https://mongodb.com/releases/8.0", "published_at": "2026-05-01T00:00:00Z", "product": "server", "version": "8.0"}])[0]
    assert signal.metadata["product"] == "server"
    assert signal.metadata["version"] == "8.0"


def test_mongodb_changelog_missing_url_fallback_id() -> None:
    signal = parse_mongodb_changelog([{"title": "Atlas update", "date": "2026-05-01T00:00:00Z", "version": "2026.05"}])[0]
    assert signal.url.startswith("mongodb_changelog://")
    assert signal.id == parse_mongodb_changelog([{"title": "Atlas update", "date": "2026-05-01T00:00:00Z", "version": "2026.05"}])[0].id


def test_mongodb_changelog_empty_and_malformed_items() -> None:
    assert parse_mongodb_changelog([]) == []
    assert parse_mongodb_changelog([{"summary": "missing title"}, "bad"]) == []
