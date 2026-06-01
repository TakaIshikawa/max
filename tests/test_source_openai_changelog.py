from __future__ import annotations

from datetime import datetime, timezone

import pytest

from max.sources.openai_changelog import OpenAIChangelogAdapter


@pytest.mark.asyncio
async def test_openai_changelog_maps_model_api_entries_and_tags() -> None:
    adapter = OpenAIChangelogAdapter(config={"entries": [
        {"id": "e1", "title": "Responses API update", "url": "https://openai.com/changelog/responses-api-update", "summary": "New API behavior", "date": "2026-05-01T12:00:00Z", "tags": ["api", "models"]},
    ]})

    signals = await adapter.fetch()

    assert len(signals) == 1
    assert signals[0].title == "Responses API update"
    assert signals[0].url == "https://openai.com/changelog/responses-api-update"
    assert signals[0].published_at == datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    assert signals[0].metadata["tags"] == ["api", "models"]


@pytest.mark.asyncio
async def test_openai_changelog_handles_missing_dates_and_stable_ids() -> None:
    adapter = OpenAIChangelogAdapter(config={"entries": [
        {"title": "Model release", "url": "https://openai.com/changelog/model-release/", "tags": "model, api"},
    ]})

    signals = await adapter.fetch()

    assert signals[0].published_at is None
    assert signals[0].id == "openai_changelog:model-release"
    assert signals[0].tags == ["model", "api"]


@pytest.mark.asyncio
async def test_openai_changelog_empty_and_unusable_payloads() -> None:
    adapter = OpenAIChangelogAdapter(config={"entries": [{"title": "Missing URL"}, "bad"]})

    assert await adapter.fetch() == []
