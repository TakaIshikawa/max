from __future__ import annotations

from max.sources.grafana_changelog import parse_grafana_changelog


def test_grafana_changelog_parses_product_and_version() -> None:
    signal = parse_grafana_changelog([{"title": "Grafana 12", "url": "https://grafana.com/changelog/12", "product": "grafana", "version": "12.0", "published_at": "2026-05-01T00:00:00Z"}])[0]
    assert signal.metadata["product"] == "grafana"
    assert signal.metadata["version"] == "12.0"


def test_grafana_changelog_deterministic_across_input_ordering() -> None:
    left = [{"title": "B", "url": "https://grafana/b", "published_at": "2026-02-01T00:00:00Z"}, {"title": "A", "url": "https://grafana/a", "published_at": "2026-01-01T00:00:00Z"}]
    right = list(reversed(left))
    assert [signal.id for signal in parse_grafana_changelog(left)] == [signal.id for signal in parse_grafana_changelog(right)]


def test_grafana_changelog_missing_version_empty_and_invalid() -> None:
    signal = parse_grafana_changelog([{"title": "Cloud update", "url": "https://grafana/cloud"}])[0]
    assert "version" not in signal.metadata
    assert parse_grafana_changelog([]) == []
    assert parse_grafana_changelog([{"title": "missing url"}, "bad"]) == []
