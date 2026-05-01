"""Tests for the JetBrains Marketplace source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.jetbrains_marketplace import (
    JETBRAINS_MARKETPLACE_PLUGIN,
    JETBRAINS_MARKETPLACE_SEARCH,
    JetBrainsMarketplaceAdapter,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


SEARCH_RESPONSE = {
    "plugins": [
        {
            "id": 20185,
            "xmlId": "com.github.copilot",
            "name": "GitHub Copilot",
            "vendor": "GitHub",
            "preview": "AI pair programmer for JetBrains IDEs.",
            "downloads": 1200000,
            "rating": 4.6,
            "tags": ["AI", "Code completion"],
            "updatedDate": "2026-04-20T12:30:00Z",
            "link": "/plugin/20185-github-copilot",
        },
        {
            "id": 24147,
            "xmlId": "dev.continue.intellij",
            "name": "Continue",
            "vendor": {"name": "Continue"},
            "preview": "Open-source coding agent plugin.",
            "downloads": 250000,
            "rating": {"average": 4.4},
            "tags": ["agent", "llm"],
        },
    ]
}

DETAIL_RESPONSE = {
    "id": 20185,
    "xmlId": "com.github.copilot",
    "name": "GitHub Copilot",
    "vendor": {"name": "GitHub"},
    "description": "AI pair programmer for JetBrains IDEs with chat and completions.",
    "downloads": 1250000,
    "rating": {"average": 4.7},
    "ratingCount": 3200,
    "version": "1.5.0",
    "tags": ["AI", "Code completion", "assistant"],
    "updateDate": 1776688200000,
    "link": "https://plugins.jetbrains.com/plugin/20185-github-copilot",
}

DIRECT_RESPONSE = {
    "id": "24147",
    "xmlId": "dev.continue.intellij",
    "name": "Continue",
    "vendor": {"name": "Continue"},
    "description": "Open-source coding agent plugin for JetBrains IDEs.",
    "downloadCount": 250000,
    "averageRating": 4.4,
    "version": "0.9.0",
    "categories": ["AI", "Developer Tools"],
    "updatedDate": "2026-04-19T10:15:00Z",
}


def test_jetbrains_marketplace_adapter_properties() -> None:
    adapter = JetBrainsMarketplaceAdapter()

    assert adapter.name == "jetbrains_marketplace"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.plugin_ids == []
    assert adapter.max_items is None


def test_jetbrains_marketplace_adapter_custom_config_and_aliases() -> None:
    adapter = JetBrainsMarketplaceAdapter(
        config={
            "queries": ["agent"],
            "watchlist_terms": ["mcp"],
            "plugin_ids": [20185, " 24147 ", 20185, "", object()],
            "max_items": "5",
        }
    )

    assert adapter.queries == ["agent", "mcp"]
    assert adapter.plugin_ids == ["20185", "24147"]
    assert adapter.max_items == 5


@pytest.mark.asyncio
async def test_jetbrains_marketplace_fetch_emits_signals_from_search_and_detail() -> None:
    adapter = JetBrainsMarketplaceAdapter(config={"queries": ["agent"]})

    with patch("max.sources.jetbrains_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: SEARCH_RESPONSE),
            MagicMock(json=lambda: DETAIL_RESPONSE),
            MagicMock(json=lambda: DIRECT_RESPONSE),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args_list[0].args[0] == JETBRAINS_MARKETPLACE_SEARCH
    assert mock_fetch.call_args_list[0].kwargs["params"] == {
        "search": "agent",
        "page": 1,
        "size": 10,
    }
    assert mock_fetch.call_args_list[1].args[0] == JETBRAINS_MARKETPLACE_PLUGIN.format(
        plugin_id="20185"
    )

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "jetbrains_marketplace"
    assert first.title == "GitHub Copilot@1.5.0"
    assert first.content == "AI pair programmer for JetBrains IDEs with chat and completions."
    assert first.url == "https://plugins.jetbrains.com/plugin/20185-github-copilot"
    assert first.author == "GitHub"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["AI", "Code completion", "assistant", "agent"]
    assert first.credibility > 0.8
    assert first.metadata["plugin_id"] == "20185"
    assert first.metadata["xml_id"] == "com.github.copilot"
    assert first.metadata["vendor"] == "GitHub"
    assert first.metadata["downloads"] == 1250000
    assert first.metadata["average_rating"] == 4.7
    assert first.metadata["rating_count"] == 3200
    assert first.metadata["source_url"] == first.url
    assert first.metadata["search_query"] == "agent"


@pytest.mark.asyncio
async def test_jetbrains_marketplace_fetches_plugin_ids_when_queries_empty() -> None:
    adapter = JetBrainsMarketplaceAdapter(config={"queries": [], "plugin_ids": ["24147"]})

    with patch("max.sources.jetbrains_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: DIRECT_RESPONSE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == JETBRAINS_MARKETPLACE_PLUGIN.format(plugin_id="24147")
    assert mock_fetch.call_args.kwargs["params"] == {}
    assert signals[0].title == "Continue@0.9.0"
    assert signals[0].metadata["requested_plugin_id"] == "24147"
    assert signals[0].metadata["source_url"] == "https://plugins.jetbrains.com/plugin/24147"


@pytest.mark.asyncio
async def test_jetbrains_marketplace_deduplicates_search_and_exact_lookup_and_respects_limit() -> None:
    adapter = JetBrainsMarketplaceAdapter(
        config={"queries": ["agent"], "plugin_ids": ["20185", "24147"]}
    )

    with patch("max.sources.jetbrains_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: SEARCH_RESPONSE),
            MagicMock(json=lambda: DETAIL_RESPONSE),
        ]

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["plugin_id"] == "20185"
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_jetbrains_marketplace_falls_back_to_search_payload_when_detail_fails() -> None:
    adapter = JetBrainsMarketplaceAdapter(config={"queries": ["agent"]})
    response = {"plugins": [SEARCH_RESPONSE["plugins"][0]]}

    with patch("max.sources.jetbrains_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: response),
            AdapterFetchError("jetbrains_marketplace", 500, "detail-url"),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "GitHub Copilot"
    assert signals[0].content == "AI pair programmer for JetBrains IDEs."
    assert signals[0].metadata["downloads"] == 1200000
    assert signals[0].metadata["average_rating"] == 4.6


@pytest.mark.asyncio
async def test_jetbrains_marketplace_skips_failed_exact_lookup() -> None:
    adapter = JetBrainsMarketplaceAdapter(config={"queries": [], "plugin_ids": ["missing"]})

    with patch("max.sources.jetbrains_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("jetbrains_marketplace", 404, "detail-url")

        signals = await adapter.fetch(limit=10)

    assert signals == []


def test_jetbrains_marketplace_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("jetbrains_marketplace")
    metadata = get_adapter_metadata()["jetbrains_marketplace"]

    assert isinstance(adapter, JetBrainsMarketplaceAdapter)
    assert metadata.config_keys == ["queries", "plugin_ids", "plugins", "max_items"]
    assert "JetBrains Marketplace" in metadata.description
