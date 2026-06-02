from __future__ import annotations

import pytest

from max.sources.postman_changelog import PostmanChangelogAdapter


@pytest.mark.asyncio
async def test_postman_changelog_adapter_converts_mocked_entries_to_signals() -> None:
    signals = await PostmanChangelogAdapter(
        {
            "entries": [
                {
                    "title": "Collection runner improvements",
                    "url": "https://postman.example/changelog/1",
                    "summary": "New collection workflow support.",
                    "tags": ["collections"],
                    "category": "feature",
                    "published_at": "2026-05-01T00:00:00Z",
                }
            ]
        }
    ).fetch()

    assert len(signals) == 1
    assert signals[0].source_adapter == "postman_changelog"
    assert signals[0].metadata["workflow_topic"] == "collections"
    assert signals[0].metadata["change_category"] == "feature"
    assert signals[0].tags == ["postman", "collections"]


@pytest.mark.asyncio
async def test_postman_changelog_adapter_dedupes_urls_and_honors_limit() -> None:
    signals = await PostmanChangelogAdapter(
        {
            "entries": [
                {"title": "API client beta", "url": "https://postman.example/a", "tags": ["client"]},
                {"title": "Duplicate", "url": "https://postman.example/a", "tags": ["monitoring"]},
                {"title": "Mock server update", "url": "https://postman.example/b", "tags": ["mock servers"]},
            ]
        }
    ).fetch(limit=1)

    assert [signal.url for signal in signals] == ["https://postman.example/a"]
    assert signals[0].metadata["workflow_topic"] == "api_client"
