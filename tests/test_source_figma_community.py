"""Tests for the Figma Community source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.figma_community import (
    FIGMA_COMMUNITY_SEARCH_URL,
    FigmaCommunityAdapter,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


MOCK_SEARCH = {
    "results": [
        {
            "resource": {
                "id": "123",
                "type": "plugin",
                "name": "Design Lint",
                "description": "Find design system drift before handoff.",
                "url": "/community/plugin/123/design-lint",
                "creator": {"name": "Acme Design"},
                "published_at": "2025-02-03T12:00:00Z",
                "likes_count": 1200,
                "duplicate_count": 0,
                "category": "Developer tools",
                "tags": ["handoff", "qa"],
            }
        },
        {
            "id": "file-9",
            "resource_type": "file",
            "name": "Creator CRM Template",
            "description": "A workspace template for sponsorship pipelines.",
            "community_url": "https://www.figma.com/community/file/file-9/creator-crm-template",
            "author": {"handle": "workflowlabs"},
            "created_at": "2024-12-01T08:30:00+00:00",
            "likes": "450",
            "duplicates": "2,100",
            "category_name": "Templates",
            "tag_names": ["creator economy", "crm"],
        },
        {
            "id": "123",
            "type": "plugin",
            "name": "Design Lint Duplicate",
            "url": "/community/plugin/123/design-lint",
        },
    ]
}


def test_figma_community_adapter_properties() -> None:
    adapter = FigmaCommunityAdapter()

    assert adapter.name == "figma_community"
    assert adapter.source_type == SignalSourceType.MARKETPLACE.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.tags == []
    assert adapter.sort == "popular"
    assert adapter.include_plugins is True
    assert adapter.include_files is True
    assert adapter.resource_types == ["plugin", "file"]


def test_figma_community_adapter_custom_config_and_watchlist() -> None:
    adapter = FigmaCommunityAdapter(
        config={
            "queries": ["agent UI"],
            "watchlist_terms": ["canvas"],
            "tags": ["Developer tools"],
            "sort": "recent",
            "include_plugins": "false",
            "include_files": True,
            "max_items": 5,
        }
    )

    assert adapter.queries == ["agent UI", "canvas"]
    assert adapter.tags == ["Developer tools"]
    assert adapter.sort == "recent"
    assert adapter.include_plugins is False
    assert adapter.include_files is True
    assert adapter.resource_types == ["file"]
    assert adapter.max_items == 5


@pytest.mark.asyncio
async def test_figma_community_fetch_emits_normalized_signals() -> None:
    adapter = FigmaCommunityAdapter(config={"queries": ["handoff"], "include_files": False})

    with patch("max.sources.figma_community.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == FIGMA_COMMUNITY_SEARCH_URL
    assert mock_fetch.call_args.kwargs["params"] == {
        "query": "handoff",
        "resource_type": "plugin",
        "sort": "popular",
        "limit": 10,
    }

    first = signals[0]
    assert first.id == "figma_community:plugin:123"
    assert first.source_type == SignalSourceType.MARKETPLACE
    assert first.source_adapter == "figma_community"
    assert first.title == "Figma plugin: Design Lint"
    assert first.content == "Find design system drift before handoff."
    assert first.url == "https://www.figma.com/community/plugin/123/design-lint"
    assert first.author == "Acme Design"
    assert first.published_at is not None
    assert first.tags == ["figma", "plugin", "handoff", "qa", "Developer tools"]
    assert first.credibility > 0.6
    assert first.metadata["resource_type"] == "plugin"
    assert first.metadata["resource_id"] == "123"
    assert first.metadata["likes_count"] == 1200
    assert first.metadata["duplicate_count"] == 0
    assert first.metadata["category"] == "Developer tools"
    assert first.metadata["search_query"] == "handoff"

    second = signals[1]
    assert second.id == "figma_community:file:file-9"
    assert second.author == "workflowlabs"
    assert second.metadata["duplicates_count"] == 2100
    assert "creator economy" in second.tags


@pytest.mark.asyncio
async def test_figma_community_respects_limit_and_deduplicates_repeated_results() -> None:
    adapter = FigmaCommunityAdapter(
        config={"queries": ["handoff"], "include_plugins": True, "include_files": False}
    )

    payload = {
        "resources": [
            {
                "id": "a",
                "type": "plugin",
                "name": "One",
                "url": "/community/plugin/a/one",
                "likes_count": 5,
            },
            {
                "id": "b",
                "type": "plugin",
                "name": "Two",
                "url": "/community/plugin/b/two",
                "likes_count": 4,
            },
            {
                "id": "b",
                "type": "plugin",
                "name": "Two Again",
                "url": "/community/plugin/b/two",
            },
            {
                "id": "c",
                "type": "plugin",
                "name": "Three",
                "url": "/community/plugin/c/three",
            },
        ]
    }

    with patch("max.sources.figma_community.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: payload)

        signals = await adapter.fetch(limit=2)

    assert [signal.metadata["resource_id"] for signal in signals] == ["a", "b"]
    assert mock_fetch.call_args.kwargs["params"]["limit"] == 2


@pytest.mark.asyncio
async def test_figma_community_filters_by_tags() -> None:
    adapter = FigmaCommunityAdapter(
        config={"queries": ["handoff"], "tags": ["Developer tools"], "include_files": False}
    )

    with patch("max.sources.figma_community.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["resource_id"] for signal in signals] == ["123"]


@pytest.mark.asyncio
async def test_figma_community_returns_empty_for_empty_payload() -> None:
    adapter = FigmaCommunityAdapter(config={"queries": ["handoff"], "include_files": False})

    with patch("max.sources.figma_community.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"results": []})

        assert await adapter.fetch(limit=10) == []


@pytest.mark.asyncio
async def test_figma_community_handles_fetch_errors_gracefully() -> None:
    adapter = FigmaCommunityAdapter(config={"queries": ["handoff"], "include_files": False})

    with patch("max.sources.figma_community.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("figma_community", 500, FIGMA_COMMUNITY_SEARCH_URL)

        assert await adapter.fetch(limit=10) == []
