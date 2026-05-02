"""Tests for the Deno/JSR registry source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.deno_registry import (
    DenoRegistryAdapter,
    JSR_API_BASE,
    JSR_REGISTRY_BASE,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


MOCK_SEARCH = {
    "items": [
        {
            "scope": "oak",
            "name": "oak",
            "description": "A middleware framework for Deno, Node.js, Bun, and Workers.",
            "latestVersion": "17.2.0",
            "downloads": 15244,
            "score": 94,
            "updatedAt": "2025-12-03T10:30:00Z",
            "runtimeCompat": ["deno", "node", "bun"],
            "tags": ["http", "middleware"],
        },
        {
            "package": "@std/path",
            "description": "Path utilities for Deno.",
            "version": "1.0.9",
            "downloadCount": "45,000",
            "jsrScore": 0.98,
        },
    ]
}

MOCK_PACKAGE = {
    "scope": "std",
    "name": "http",
    "description": "HTTP utilities for Deno.",
    "versions": {
        "1.0.0": {"publishedAt": "2024-09-01T00:00:00Z"},
        "1.0.12": {"publishedAt": "2025-01-08T00:00:00Z"},
    },
}


def test_deno_registry_adapter_properties() -> None:
    adapter = DenoRegistryAdapter()

    assert adapter.name == "deno_registry"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.categories == []
    assert adapter.package_names == []
    assert adapter.max_results == 10
    assert adapter.api_base_url == JSR_API_BASE
    assert adapter.registry_base_url == JSR_REGISTRY_BASE


def test_deno_registry_adapter_custom_config() -> None:
    adapter = DenoRegistryAdapter(
        config={
            "queries": ["http"],
            "categories": ["testing"],
            "packages": ["@std/http"],
            "watchlist_terms": ["mcp"],
            "max_results": 5,
            "api_base_url": "https://api.example.test/",
            "registry_base_url": "https://registry.example.test/",
        }
    )

    assert adapter.queries == ["http", "mcp"]
    assert adapter.categories == ["testing", "mcp"]
    assert adapter.package_names == ["@std/http", "mcp"]
    assert adapter.max_results == 5
    assert adapter.api_base_url == "https://api.example.test"
    assert adapter.registry_base_url == "https://registry.example.test"


@pytest.mark.asyncio
async def test_deno_registry_fetch_emits_normalized_search_signals() -> None:
    adapter = DenoRegistryAdapter(config={"queries": ["web framework"], "max_results": 2})

    with patch("max.sources.deno_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == f"{JSR_API_BASE}/packages"
    assert mock_fetch.call_args.kwargs["params"] == {"query": "web framework", "limit": 2}

    first = signals[0]
    assert first.id.startswith("deno_registry:")
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "deno_registry"
    assert first.title == "@oak/oak@17.2.0"
    assert first.content.startswith("A middleware framework")
    assert first.url == "https://jsr.io/@oak/oak"
    assert first.published_at.isoformat() == "2025-12-03T10:30:00+00:00"
    assert first.tags == [
        "deno",
        "jsr",
        "typescript",
        "web framework",
        "node",
        "bun",
        "http",
        "middleware",
    ]
    assert first.credibility > 0.9
    assert first.metadata["package_ecosystem"] == "deno"
    assert first.metadata["registry"] == "jsr"
    assert first.metadata["package_scope"] == "oak"
    assert first.metadata["package_name"] == "oak"
    assert first.metadata["package_specifier"] == "@oak/oak"
    assert first.metadata["latest_version"] == "17.2.0"
    assert first.metadata["downloads"] == 15244
    assert first.metadata["score"] == 94.0
    assert first.metadata["search_query"] == "web framework"
    assert first.metadata["lookup_type"] == "search"


@pytest.mark.asyncio
async def test_deno_registry_fetches_exact_package_metadata() -> None:
    adapter = DenoRegistryAdapter(config={"package_names": ["@std/http"], "queries": []})

    with patch("max.sources.deno_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_PACKAGE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == f"{JSR_REGISTRY_BASE}/@std/http/meta.json"

    signal = signals[0]
    assert signal.title == "@std/http@1.0.12"
    assert signal.url == "https://jsr.io/@std/http"
    assert signal.metadata["lookup_type"] == "package"
    assert signal.metadata["search_query"] is None
    assert signal.metadata["api_url"] == "https://jsr.io/@std/http/meta.json"


@pytest.mark.asyncio
async def test_deno_registry_fetch_returns_empty_for_no_results() -> None:
    adapter = DenoRegistryAdapter(config={"queries": ["missing"]})

    with patch("max.sources.deno_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"items": []})

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_deno_registry_fetch_logs_and_skips_request_failures(caplog) -> None:
    adapter = DenoRegistryAdapter(config={"queries": ["http"]})

    with patch("max.sources.deno_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError("deno_registry", 503, f"{JSR_API_BASE}/packages")

        signals = await adapter.fetch(limit=10)

    assert signals == []
    assert "failed to fetch Deno package search results" in caplog.text


@pytest.mark.asyncio
async def test_deno_registry_signal_ids_are_deterministic() -> None:
    adapter = DenoRegistryAdapter(config={"queries": ["web framework"]})

    with patch("max.sources.deno_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)
        first = await adapter.fetch(limit=10)
        second = await adapter.fetch(limit=10)

    assert [signal.id for signal in first] == [signal.id for signal in second]
