"""Tests for the Eclipse Marketplace source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.eclipse_marketplace import (
    ECLIPSE_MARKETPLACE_SEARCH,
    ECLIPSE_MARKETPLACE_TAXONOMY,
    EclipseMarketplaceAdapter,
    _DEFAULT_QUERIES,
    parse_eclipse_marketplace_response,
)
from max.types.signal import SignalSourceType


SEARCH_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<marketplace>
  <search count="2" term="ai">
    <node id="12345" name="Code Recommenders" url="https://marketplace.eclipse.org/content/code-recommenders">
      <type>resource</type>
      <categories>
        <category id="6" name="Editor" url="https://marketplace.eclipse.org/listings/category/editor" />
        <category id="24" name="IDE" url="https://marketplace.eclipse.org/listings/category/ide" />
      </categories>
      <tags>
        <tag>AI</tag>
        <tag>Java</tag>
      </tags>
      <owner>Eclipse Foundation</owner>
      <summary>Intelligent code completion tools for Eclipse IDE.</summary>
      <license>Free EPL</license>
      <status>Production/Stable</status>
      <companyurl>https://www.eclipse.org</companyurl>
      <updateurl>https://download.eclipse.org/recommenders/update-site/</updateurl>
      <installstotal>125000</installstotal>
      <favorited>850</favorited>
      <rating>4.5</rating>
      <ratingcount>42</ratingcount>
      <changed>2026-04-20T12:30:00Z</changed>
    </node>
    <node id="67890" name="AI Assistant" url="/content/ai-assistant">
      <owner>Example Corp</owner>
      <body>Assistant workflows for Eclipse users.</body>
      <installs>50000</installs>
      <favorites>300</favorites>
      <updated>1776688200</updated>
    </node>
  </search>
</marketplace>
"""

SECOND_PAGE_RESPONSE = """<marketplace>
  <search count="1" term="ai">
    <node id="12345" name="Code Recommenders" url="https://marketplace.eclipse.org/content/code-recommenders" />
    <node id="99999" name="MCP Tools" url="https://marketplace.eclipse.org/content/mcp-tools">
      <owner>Tooling Team</owner>
      <description>MCP integrations for Eclipse.</description>
      <downloads>9000</downloads>
    </node>
  </search>
</marketplace>
"""

SPARSE_RESPONSE = """<marketplace>
  <recent count="1">
    <node id="minimal" name="Minimal Plugin" url="https://marketplace.eclipse.org/content/minimal-plugin" />
  </recent>
</marketplace>
"""


def test_eclipse_marketplace_adapter_properties() -> None:
    adapter = EclipseMarketplaceAdapter()

    assert adapter.name == "eclipse_marketplace"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.sections == ["recent"]
    assert adapter.categories == []
    assert adapter.max_pages == 1
    assert adapter.max_items is None
    assert adapter.timeout == 30.0


def test_eclipse_marketplace_adapter_custom_config_and_aliases() -> None:
    adapter = EclipseMarketplaceAdapter(
        config={
            "queries": ["ai"],
            "watchlist_terms": ["mcp"],
            "sections": ["recent", "favorites", "unknown"],
            "taxonomy_terms": ["6,31", " 24 "],
            "max_pages": "2",
            "max_results": "5",
            "timeout": "12.5",
        }
    )

    assert adapter.queries == ["ai", "mcp"]
    assert adapter.sections == ["recent", "favorites"]
    assert adapter.categories == ["6,31", "24"]
    assert adapter.max_pages == 2
    assert adapter.max_items == 5
    assert adapter.timeout == 12.5


def test_parse_eclipse_marketplace_response_without_network() -> None:
    rows = parse_eclipse_marketplace_response(SEARCH_RESPONSE)

    assert len(rows) == 2
    first = rows[0]
    assert first["id"] == "12345"
    assert first["name"] == "Code Recommenders"
    assert first["owner"] == "Eclipse Foundation"
    assert first["categories"] == [
        {
            "id": "6",
            "name": "Editor",
            "url": "https://marketplace.eclipse.org/listings/category/editor",
        },
        {
            "id": "24",
            "name": "IDE",
            "url": "https://marketplace.eclipse.org/listings/category/ide",
        },
    ]
    assert first["tags"] == ["AI", "Java"]
    assert first["install_count"] == 125000
    assert first["favorites"] == 850
    assert first["rating"] == 4.5
    assert first["updated_at"] == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert parse_eclipse_marketplace_response("<not xml") == []


@pytest.mark.asyncio
async def test_eclipse_marketplace_fetch_emits_signals_from_search_results() -> None:
    adapter = EclipseMarketplaceAdapter(config={"queries": ["ai"], "sections": []})

    with patch("max.sources.eclipse_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == ECLIPSE_MARKETPLACE_SEARCH.format(query="ai")
    assert mock_fetch.call_args.kwargs["params"] == {"page_num": 1, "limit": 10}

    first = signals[0]
    assert first.id == "eclipse-marketplace:12345"
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "eclipse_marketplace"
    assert first.title == "Code Recommenders"
    assert "Installs: 125,000" in first.content
    assert "Favorites: 850" in first.content
    assert "Rating: 4.5/5" in first.content
    assert first.url == "https://marketplace.eclipse.org/content/code-recommenders"
    assert first.author == "Eclipse Foundation"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["eclipse", "marketplace", "ide-plugin", "Editor", "IDE", "AI", "Java", "ai"]
    assert first.credibility > 0.8
    assert first.metadata["signal_role"] == "market"
    assert first.metadata["signal_kind"] == "plugin_activity"
    assert first.metadata["evidence_type"] == "marketplace_listing"
    assert first.metadata["marketplace"] == "eclipse_marketplace"
    assert first.metadata["plugin_id"] == "12345"
    assert first.metadata["install_count"] == 125000
    assert first.metadata["favorites"] == 850
    assert first.metadata["average_rating"] == 4.5
    assert first.metadata["rating_count"] == 42
    assert first.metadata["categories"] == ["Editor", "IDE"]
    assert first.metadata["license"] == "Free EPL"
    assert first.metadata["status"] == "Production/Stable"
    assert first.metadata["search_query"] == "ai"

    second = signals[1]
    assert second.url == "https://marketplace.eclipse.org/content/ai-assistant"
    assert second.metadata["updated_at"] == "2026-04-20T12:30:00+00:00"


@pytest.mark.asyncio
async def test_eclipse_marketplace_handles_missing_optional_fields() -> None:
    adapter = EclipseMarketplaceAdapter(config={"queries": ["minimal"], "sections": []})

    with patch("max.sources.eclipse_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=SPARSE_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Minimal Plugin"
    assert signal.content == "Minimal Plugin"
    assert signal.author is None
    assert signal.published_at is None
    assert signal.metadata["install_count"] is None
    assert signal.metadata["favorites"] is None
    assert signal.metadata["average_rating"] is None
    assert signal.metadata["categories"] == []
    assert signal.tags == ["eclipse", "marketplace", "ide-plugin", "minimal"]


@pytest.mark.asyncio
async def test_eclipse_marketplace_paginates_and_deduplicates_results() -> None:
    adapter = EclipseMarketplaceAdapter(config={"queries": ["ai"], "sections": [], "max_pages": 2})

    with patch("max.sources.eclipse_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(text=SEARCH_RESPONSE),
            MagicMock(text=SECOND_PAGE_RESPONSE),
        ]

        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["plugin_id"] for signal in signals] == ["12345", "67890", "99999"]
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"page_num": 1, "limit": 5}
    assert mock_fetch.call_args_list[1].kwargs["params"] == {"page_num": 2, "limit": 5}


@pytest.mark.asyncio
async def test_eclipse_marketplace_fetches_category_listing_with_query_parameters() -> None:
    adapter = EclipseMarketplaceAdapter(config={"queries": [], "sections": [], "categories": ["6,31"]})

    with patch("max.sources.eclipse_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(text=SPARSE_RESPONSE)

        signals = await adapter.fetch(limit=3)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == ECLIPSE_MARKETPLACE_TAXONOMY.format(term="6,31")
    assert mock_fetch.call_args.kwargs["params"] == {"page_num": 1, "limit": 3}
    assert signals[0].metadata["category"] == "6,31"


@pytest.mark.asyncio
async def test_eclipse_marketplace_network_failures_and_malformed_payloads_are_skipped() -> None:
    adapter = EclipseMarketplaceAdapter(
        config={"queries": ["broken", "malformed", "ai"], "sections": [], "max_pages": 1}
    )

    with patch("max.sources.eclipse_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            AdapterFetchError("eclipse_marketplace", 500, "broken-url"),
            MagicMock(text="<not xml"),
            MagicMock(text=SPARSE_RESPONSE),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["plugin_id"] == "minimal"
    assert signals[0].metadata["search_query"] == "ai"


def test_eclipse_marketplace_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("eclipse_marketplace")
    metadata = get_adapter_metadata()["eclipse_marketplace"]

    assert isinstance(adapter, EclipseMarketplaceAdapter)
    assert metadata.config_keys == [
        "queries",
        "sections",
        "categories",
        "taxonomy_terms",
        "max_pages",
        "max_items",
        "max_results",
        "timeout",
    ]
    assert "Eclipse Marketplace" in metadata.description
