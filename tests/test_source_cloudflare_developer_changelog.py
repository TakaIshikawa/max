from __future__ import annotations

from max.sources.cloudflare_developer_changelog import parse_cloudflare_developer_changelog
from max.sources.registry import get_adapter_class


def test_cloudflare_developer_changelog_maps_entries() -> None:
    signals = parse_cloudflare_developer_changelog(
        [
            {
                "title": "Workers AI binding update",
                "url": "https://developers.cloudflare.com/changelog/workers-ai-binding",
                "date": "2026-05-02T00:00:00Z",
                "summary": "Workers AI binding improvements.",
                "product": "Workers AI",
                "category": "AI",
            },
            {
                "title": "R2 lifecycle rules",
                "url": "https://developers.cloudflare.com/changelog/r2-lifecycle",
                "content": "New lifecycle controls.",
                "product": "R2",
            },
        ]
    )

    assert [signal.title for signal in signals] == ["Workers AI binding update", "R2 lifecycle rules"]
    assert signals[0].source_adapter == "cloudflare_developer_changelog"
    assert signals[0].metadata["product"] == "Workers AI"
    assert signals[0].metadata["category"] == "AI"
    assert signals[0].published_at is not None
    assert signals[1].content == "New lifecycle controls."


def test_cloudflare_developer_changelog_stable_ids_defaults_empty_and_registry() -> None:
    payload = [{"title": "Cache Rules", "url": "https://developers.cloudflare.com/changelog/cache-rules"}]

    assert parse_cloudflare_developer_changelog(payload)[0].id == parse_cloudflare_developer_changelog(payload)[0].id
    assert parse_cloudflare_developer_changelog(payload)[0].metadata == {"source_name": "Cloudflare Developer Changelog"}
    assert parse_cloudflare_developer_changelog({"entries": []}) == []
    assert get_adapter_class("cloudflare_developer_changelog").__name__ == "CloudflareDeveloperChangelogAdapter"
