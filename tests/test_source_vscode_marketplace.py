"""Tests for the Visual Studio Code Marketplace source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.vscode_marketplace import (
    VSCODE_MARKETPLACE_QUERY,
    VSCodeMarketplaceAdapter,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


SEARCH_RESPONSE = {
    "results": [
        {
            "extensions": [
                {
                    "publisher": {
                        "publisherName": "Continue",
                        "displayName": "Continue",
                    },
                    "extensionName": "continue",
                    "displayName": "Continue",
                    "shortDescription": "Open-source coding agent extension.",
                    "categories": ["Programming Languages", "Machine Learning"],
                    "statistics": [
                        {"statisticName": "install", "value": 125000},
                        {"statisticName": "averagerating", "value": 4.7},
                        {"statisticName": "ratingcount", "value": 900},
                    ],
                    "versions": [
                        {
                            "version": "1.2.3",
                            "lastUpdated": "2026-04-20T12:30:00Z",
                            "properties": [
                                {
                                    "key": "Microsoft.VisualStudio.Code.ExtensionTags",
                                    "value": "agent,llm",
                                },
                                {
                                    "key": "Microsoft.VisualStudio.Services.Links.Source",
                                    "value": "https://github.com/continuedev/continue",
                                },
                            ],
                        }
                    ],
                },
                {
                    "publisher": {"publisherName": "GitHub"},
                    "extensionName": "copilot-chat",
                    "displayName": "GitHub Copilot Chat",
                    "shortDescription": "Chat with your coding assistant.",
                    "categories": ["Other"],
                    "statistics": [
                        {"statisticName": "install", "value": 50000},
                        {"statisticName": "downloadCount", "value": 70000},
                        {"statisticName": "averagerating", "value": 4.3},
                    ],
                    "versions": [
                        {
                            "version": "0.9.0",
                            "lastUpdated": "2026-04-18T09:00:00Z",
                            "properties": [
                                {
                                    "key": "Microsoft.VisualStudio.Code.ExtensionTags",
                                    "value": "assistant,copilot",
                                }
                            ],
                        }
                    ],
                },
            ]
        }
    ]
}

DIRECT_RESPONSE = {
    "results": [
        {
            "extensions": [
                {
                    "publisher": {
                        "publisherName": "OpenAI",
                        "displayName": "OpenAI",
                    },
                    "extensionName": "chatgpt",
                    "displayName": "ChatGPT",
                    "shortDescription": "Use ChatGPT in VS Code.",
                    "categories": ["AI"],
                    "statistics": [
                        {"statisticName": "install", "value": 82000},
                        {"statisticName": "averagerating", "value": 4.5},
                    ],
                    "versions": [
                        {
                            "version": "2.0.0",
                            "lastUpdated": "2026-04-19T10:15:00Z",
                            "properties": [
                                {
                                    "key": "Microsoft.VisualStudio.Code.ExtensionTags",
                                    "value": "chatgpt,agent",
                                },
                                {
                                    "key": "Microsoft.VisualStudio.Services.Links.GitHub",
                                    "value": "https://github.com/openai/chatgpt-vscode",
                                },
                            ],
                        }
                    ],
                }
            ]
        }
    ]
}


def test_vscode_marketplace_adapter_properties() -> None:
    adapter = VSCodeMarketplaceAdapter()

    assert adapter.name == "vscode_marketplace"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.extensions == []
    assert adapter.max_items is None
    assert adapter.categories == []
    assert adapter.tag_filters == []


def test_vscode_marketplace_adapter_custom_config_and_aliases() -> None:
    adapter = VSCodeMarketplaceAdapter(
        config={
            "queries": ["agent"],
            "watchlist_terms": ["mcp"],
            "extension_identifiers": [
                "OpenAI.chatgpt",
                "GitHub/copilot-chat",
                "bad",
                "OpenAI.chatgpt",
            ],
            "max_items": "5",
            "categories": ["AI"],
            "tags": ["Agent"],
        }
    )

    assert adapter.queries == ["agent", "mcp"]
    assert adapter.extensions == ["OpenAI.chatgpt", "GitHub/copilot-chat"]
    assert adapter.max_items == 5
    assert adapter.categories == ["ai"]
    assert adapter.tag_filters == ["agent"]


@pytest.mark.asyncio
async def test_vscode_marketplace_fetch_emits_signals_from_search_results() -> None:
    adapter = VSCodeMarketplaceAdapter(config={"queries": ["agent"]})

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == VSCODE_MARKETPLACE_QUERY
    assert mock_fetch.call_args.kwargs["method"] == "POST"
    assert mock_fetch.call_args.kwargs["params"] == {"api-version": "7.2-preview.1"}
    criteria = mock_fetch.call_args.kwargs["json"]["filters"][0]["criteria"]
    assert {"filterType": 10, "value": "agent"} in criteria
    assert {"filterType": 8, "value": "Microsoft.VisualStudio.Code"} in criteria

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "vscode_marketplace"
    assert first.title == "Continue@1.2.3"
    assert first.content == "Open-source coding agent extension."
    assert first.url == "https://marketplace.visualstudio.com/items?itemName=Continue.continue"
    assert first.author == "Continue"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.tags == ["Programming Languages", "Machine Learning", "agent", "llm"]
    assert first.credibility > 0.8
    assert first.metadata["publisher"] == "Continue"
    assert first.metadata["publisher_display_name"] == "Continue"
    assert first.metadata["name"] == "continue"
    assert first.metadata["version"] == "1.2.3"
    assert first.metadata["install_count"] == 125000
    assert first.metadata["download_count"] is None
    assert first.metadata["average_rating"] == 4.7
    assert first.metadata["rating_count"] == 900
    assert first.metadata["categories"] == ["Programming Languages", "Machine Learning"]
    assert first.metadata["tags"] == ["agent", "llm"]
    assert first.metadata["repository"] == "https://github.com/continuedev/continue"
    assert first.metadata["published_at"] == "2026-04-20T12:30:00+00:00"
    assert first.metadata["source_url"] == first.url
    assert first.metadata["search_query"] == "agent"


@pytest.mark.asyncio
async def test_vscode_marketplace_fetch_emits_signals_from_direct_extension_lookup() -> None:
    adapter = VSCodeMarketplaceAdapter(
        config={"queries": [], "extensions": ["OpenAI.chatgpt"]}
    )

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: DIRECT_RESPONSE)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    criteria = mock_fetch.call_args.kwargs["json"]["filters"][0]["criteria"]
    assert {"filterType": 7, "value": "OpenAI.chatgpt"} in criteria
    assert signals[0].title == "ChatGPT@2.0.0"
    assert signals[0].url == "https://marketplace.visualstudio.com/items?itemName=OpenAI.chatgpt"
    assert signals[0].metadata["extension_identifier"] == "OpenAI.chatgpt"
    assert signals[0].metadata["repository"] == "https://github.com/openai/chatgpt-vscode"


@pytest.mark.asyncio
async def test_vscode_marketplace_filters_by_category_and_tag() -> None:
    adapter = VSCodeMarketplaceAdapter(
        config={"queries": ["agent"], "categories": ["Programming Languages"], "tags": ["llm"]}
    )

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["publisher"] == "Continue"


@pytest.mark.asyncio
async def test_vscode_marketplace_handles_missing_optional_fields() -> None:
    adapter = VSCodeMarketplaceAdapter(config={"queries": ["minimal"]})
    response = {
        "results": [
            {
                "extensions": [
                    {
                        "publisher": {"publisherName": "Minimal"},
                        "extensionName": "extension",
                    }
                ]
            }
        ]
    }

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: response)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "extension"
    assert signal.content == "extension"
    assert signal.published_at is None
    assert signal.tags == ["minimal"]
    assert signal.metadata["version"] is None
    assert signal.metadata["install_count"] is None
    assert signal.metadata["average_rating"] is None
    assert signal.metadata["categories"] == []
    assert signal.metadata["tags"] == []
    assert signal.metadata["repository"] is None
    assert (
        signal.metadata["source_url"]
        == "https://marketplace.visualstudio.com/items?itemName=Minimal.extension"
    )


@pytest.mark.asyncio
async def test_vscode_marketplace_skips_bad_records_and_deduplicates() -> None:
    adapter = VSCodeMarketplaceAdapter(config={"queries": ["agent", "llm"]})
    first_response = {
        "results": [
            {
                "extensions": [
                    {"extensionName": "missing-publisher"},
                    {
                        "publisher": {"publisherName": "Continue"},
                        "extensionName": "continue",
                    },
                ]
            }
        ]
    }
    second_response = {
        "results": [
            {
                "extensions": [
                    {
                        "publisher": {"publisherName": "continue"},
                        "extensionName": "Continue",
                    },
                    {
                        "publisher": {"publisherName": "Other"},
                        "extensionName": "assistant",
                    },
                ]
            }
        ]
    }

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: first_response),
            MagicMock(json=lambda: second_response),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["publisher"] for signal in signals] == ["Continue", "Other"]
    assert [signal.metadata["name"] for signal in signals] == ["continue", "assistant"]


@pytest.mark.asyncio
async def test_vscode_marketplace_respects_limit_and_max_items() -> None:
    adapter = VSCodeMarketplaceAdapter(
        config={"queries": ["agent"], "extensions": ["OpenAI.chatgpt"], "max_items": 1}
    )

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["publisher"] == "Continue"
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.kwargs["json"]["filters"][0]["pageSize"] == 1


@pytest.mark.asyncio
async def test_vscode_marketplace_http_failures_return_empty_results() -> None:
    adapter = VSCodeMarketplaceAdapter(config={"queries": ["agent"]})

    with patch("max.sources.vscode_marketplace.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("vscode_marketplace", 500, "url")

        signals = await adapter.fetch(limit=10)

    assert signals == []


def test_vscode_marketplace_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("vscode_marketplace")
    metadata = get_adapter_metadata()["vscode_marketplace"]

    assert isinstance(adapter, VSCodeMarketplaceAdapter)
    assert metadata.config_keys == [
        "queries",
        "extensions",
        "extension_identifiers",
        "max_items",
        "categories",
        "tags",
    ]
    assert "Visual Studio Code Marketplace" in metadata.description
