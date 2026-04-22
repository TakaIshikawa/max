"""Tests for the MCP Registry source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.mcp_registry import (
    DEFAULT_BASE_URL,
    DEFAULT_ENDPOINT,
    McpRegistryAdapter,
)
from max.types.signal import SignalSourceType


MOCK_LISTING = {
    "servers": [
        {
            "name": "io.github.example/filesystem",
            "title": "Filesystem",
            "description": "Read and write local files through MCP.",
            "version": "1.2.3",
            "packages": [
                {
                    "registryType": "npm",
                    "identifier": "@example/filesystem-mcp",
                    "version": "1.2.3",
                    "transport": {"type": "stdio"},
                }
            ],
            "capabilities": {"resources": {"listChanged": True}, "tools": {}},
            "categories": ["developer-tools", "files"],
            "repository": {"url": "https://github.com/example/filesystem"},
            "websiteUrl": "https://example.dev/filesystem",
            "_meta": {
                "com.example.registry/trust": {
                    "stars": 1200,
                    "download_count": 50000,
                    "trust_score": 0.91,
                }
            },
            "updatedAt": "2026-04-20T12:30:00Z",
        }
    ],
    "metadata": {"count": 1},
}


def test_mcp_registry_adapter_properties() -> None:
    adapter = McpRegistryAdapter()

    assert adapter.name == "mcp_registry"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.base_url == DEFAULT_BASE_URL
    assert adapter.endpoint == DEFAULT_ENDPOINT
    assert adapter.queries == []
    assert adapter.categories == []


def test_mcp_registry_adapter_custom_config() -> None:
    adapter = McpRegistryAdapter(
        config={
            "base_url": "https://registry.example.test/",
            "endpoint": "api/servers",
            "queries": ["filesystem"],
            "categories": ["developer-tools"],
            "watchlist_terms": ["database"],
            "min_stars": "10",
            "min_score": "80",
        }
    )

    assert adapter.base_url == "https://registry.example.test"
    assert adapter.endpoint == "api/servers"
    assert adapter.queries == ["filesystem", "database"]
    assert adapter.categories == ["developer-tools", "database"]
    assert adapter.min_stars == 10
    assert adapter.min_score == 0.8


@pytest.mark.asyncio
async def test_mcp_registry_fetch_success() -> None:
    adapter = McpRegistryAdapter()

    with patch("max.sources.mcp_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_LISTING)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == "https://registry.modelcontextprotocol.io/v0.1/servers"
    assert mock_fetch.call_args.kwargs["params"] == {"limit": 10}

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "mcp_registry"
    assert signal.title == "Filesystem@1.2.3"
    assert signal.content == "Read and write local files through MCP."
    assert signal.url == (
        "https://registry.modelcontextprotocol.io/v0.1/servers/"
        "io.github.example%2Ffilesystem/versions/1.2.3"
    )
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == ["developer-tools", "files", "resources", "tools", "npm"]
    assert signal.credibility > 0.8
    assert signal.metadata["server_name"] == "io.github.example/filesystem"
    assert signal.metadata["version"] == "1.2.3"
    assert signal.metadata["registry_url"] == signal.url
    assert signal.metadata["package_urls"] == [
        "https://www.npmjs.com/package/@example/filesystem-mcp"
    ]
    assert signal.metadata["capabilities"] == ["resources", "tools"]
    assert signal.metadata["categories"] == ["developer-tools", "files"]
    assert signal.metadata["stars"] == 1200
    assert signal.metadata["downloads"] == 50000
    assert signal.metadata["score"] == 0.91
    assert signal.metadata["verified"] is True


@pytest.mark.asyncio
async def test_mcp_registry_skips_malformed_entries_and_filters_metrics() -> None:
    adapter = McpRegistryAdapter(config={"min_stars": 100, "min_score": 0.7})
    listing = {
        "servers": [
            {"description": "missing name"},
            {
                "name": "io.github.example/low-stars",
                "description": "Too few stars.",
                "_meta": {"stars": 10, "trust_score": 0.95},
            },
            {
                "name": "io.github.example/low-score",
                "description": "Too low score.",
                "_meta": {"stars": 250, "trust_score": 0.4},
            },
            {
                "name": "io.github.example/good",
                "description": "Good server.",
                "_meta": {"stars": 250, "trust_score": 0.8},
            },
        ]
    }

    with patch("max.sources.mcp_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: listing)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["server_name"] == "io.github.example/good"


@pytest.mark.asyncio
async def test_mcp_registry_respects_limit_and_pagination() -> None:
    adapter = McpRegistryAdapter()
    first_page = {
        "servers": [
            {"name": "io.github.example/one", "description": "First server."},
            {"name": "io.github.example/two", "description": "Second server."},
        ],
        "metadata": {"nextCursor": "cursor-2"},
    }
    second_page = {
        "servers": [{"name": "io.github.example/three", "description": "Third server."}],
        "metadata": {},
    }

    with patch("max.sources.mcp_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: first_page),
            MagicMock(json=lambda: second_page),
        ]

        signals = await adapter.fetch(limit=3)

    assert [signal.metadata["server_name"] for signal in signals] == [
        "io.github.example/one",
        "io.github.example/two",
        "io.github.example/three",
    ]
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"limit": 3}
    assert mock_fetch.call_args_list[1].kwargs["params"] == {"limit": 1, "cursor": "cursor-2"}


@pytest.mark.asyncio
async def test_mcp_registry_uses_configured_queries_categories_and_base_url() -> None:
    adapter = McpRegistryAdapter(
        config={
            "base_url": "https://registry.example.test",
            "queries": ["filesystem"],
            "categories": ["developer-tools"],
        }
    )
    listing = {
        "servers": [
            {
                "name": "io.github.example/filesystem",
                "description": "Filesystem server.",
                "categories": ["developer-tools"],
            }
        ]
    }

    with patch("max.sources.mcp_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: listing)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
    assert mock_fetch.call_args.args[0] == "https://registry.example.test/v0.1/servers"
    assert mock_fetch.call_args.kwargs["params"] == {"limit": 1, "search": "filesystem"}
    assert signals[0].metadata["search_query"] == "filesystem"

