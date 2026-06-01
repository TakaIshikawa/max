from __future__ import annotations

from max.sources.render_changelog import parse_render_changelog


def test_render_changelog_published_entries() -> None:
    signals = parse_render_changelog([{"title": "Web services", "url": "https://render.com/changelog/a", "date": "2026-01-01T00:00:00Z", "service": "web"}])
    assert signals[0].source_adapter == "render_changelog"
    assert signals[0].metadata["service"] == "web"
    assert signals[0].published_at is not None


def test_render_changelog_empty_and_malformed() -> None:
    assert parse_render_changelog([]) == []
    assert parse_render_changelog([{"url": "https://render.com/a"}]) == []


def test_render_changelog_stable_external_ids() -> None:
    payload = [{"title": "A", "url": "https://render.com/a"}]
    assert parse_render_changelog(payload)[0].id == parse_render_changelog(payload)[0].id
