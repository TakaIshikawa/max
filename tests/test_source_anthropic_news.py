from __future__ import annotations

from datetime import datetime, timezone

import pytest

from max.sources.anthropic_news import AnthropicNewsAdapter


@pytest.mark.asyncio
async def test_anthropic_news_maps_release_posts() -> None:
    adapter = AnthropicNewsAdapter(config={"entries": [
        {"title": "Claude release", "url": "https://www.anthropic.com/news/claude-release", "summary": "Release notes", "published_at": "2026-05-10T09:00:00Z", "category": "product"},
    ]})

    signals = await adapter.fetch()

    assert len(signals) == 1
    assert signals[0].title == "Claude release"
    assert signals[0].content == "Release notes"
    assert signals[0].published_at == datetime(2026, 5, 10, 9, tzinfo=timezone.utc)
    assert signals[0].metadata["category"] == "product"


@pytest.mark.asyncio
async def test_anthropic_news_keeps_research_category_and_absent_summary() -> None:
    adapter = AnthropicNewsAdapter(config={"entries": [
        {"title": "Research update", "url": "https://www.anthropic.com/news/research-update", "date": "2026-04-01", "category": "research"},
    ]})

    signals = await adapter.fetch()

    assert signals[0].content == "Research update"
    assert signals[0].tags == ["research"]
    assert signals[0].id == "anthropic_news:research-update"


@pytest.mark.asyncio
async def test_anthropic_news_skips_unusable_entries_and_empty_payloads() -> None:
    adapter = AnthropicNewsAdapter(config={"entries": [{"url": "https://example.test/no-title"}, {"title": "No URL"}]})

    assert await adapter.fetch() == []
