from __future__ import annotations

from max.sources.tailscale_changelog import TailscaleChangelogAdapter, parse_tailscale_changelog


def test_tailscale_changelog_parses_networking_signal() -> None:
    signals = parse_tailscale_changelog([{"title": "Subnet router update", "url": "https://tailscale.com/changelog/a", "published_at": "2026-05-04T00:00:00Z"}])

    assert signals[0].source_adapter == "tailscale_changelog"
    assert {"tailscale", "networking", "infrastructure"}.issubset(signals[0].tags)
    assert signals[0].published_at is not None


def test_tailscale_changelog_empty_payload() -> None:
    assert parse_tailscale_changelog([]) == []


def test_tailscale_changelog_malformed_entries() -> None:
    assert parse_tailscale_changelog([{"title": "missing url"}, "bad"]) == []
    assert TailscaleChangelogAdapter().name == "tailscale_changelog"
