"""Tests for the Swift Package Index source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.swift_package_index import (
    SWIFT_PACKAGE_INDEX_SEARCH,
    SwiftPackageIndexAdapter,
    _DEFAULT_QUERIES,
)
from max.types.signal import SignalSourceType


MOCK_SEARCH = {
    "results": [
        {
            "name": "Vapor",
            "description": "Server-side Swift web framework.",
            "repository_url": "https://github.com/vapor/vapor",
            "stars": 25_000,
            "score": 8.5,
            "latest_version": "4.100.0",
            "updated_at": "2026-04-18T10:30:00Z",
            "keywords": ["server", "web"],
            "categories": ["framework"],
            "license": "MIT",
        },
        {
            "packageName": "swift-argument-parser",
            "summary": "Straightforward typed command-line argument parsing.",
            "repository": {"url": "https://github.com/apple/swift-argument-parser"},
            "githubStars": "3,300",
            "search_score": 6,
            "latestRelease": "1.5.0",
            "last_activity_at": "2026-04-10T08:00:00Z",
            "tags": ["cli"],
            "categories": ["command-line"],
        },
    ]
}

MOCK_MISSING_OPTIONAL = {
    "packages": [
        {
            "name": "MinimalPackage",
            "description": None,
            "repository_url": "https://github.com/example/minimal-package",
        }
    ]
}


def test_swift_package_index_adapter_properties() -> None:
    adapter = SwiftPackageIndexAdapter()

    assert adapter.name == "swift_package_index"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.keywords == []
    assert adapter.categories == []
    assert adapter.max_results == 10


def test_swift_package_index_adapter_custom_config() -> None:
    adapter = SwiftPackageIndexAdapter(
        config={
            "queries": ["server"],
            "watchlist_terms": ["testing"],
            "keywords": ["web"],
            "categories": ["framework"],
            "max_results": 3,
        }
    )

    assert adapter.queries == ["server", "testing"]
    assert adapter.keywords == ["web", "testing"]
    assert adapter.categories == ["framework", "testing"]
    assert adapter.max_results == 3


@pytest.mark.asyncio
async def test_swift_package_index_fetch_emits_package_signals() -> None:
    adapter = SwiftPackageIndexAdapter(config={"queries": ["server"], "max_results": 5})

    with patch("max.sources.swift_package_index.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == SWIFT_PACKAGE_INDEX_SEARCH
    assert mock_fetch.call_args.kwargs["params"] == {
        "query": "server",
        "page": 1,
        "per_page": 5,
    }

    first = signals[0]
    assert first.id.startswith("swift_package_index:")
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "swift_package_index"
    assert first.title == "Vapor@4.100.0"
    assert first.content == "Server-side Swift web framework."
    assert first.url == "https://swiftpackageindex.com/vapor/vapor"
    assert first.author == "vapor"
    assert first.published_at == datetime(2026, 4, 18, 10, 30, tzinfo=timezone.utc)
    assert first.tags == [
        "swift",
        "swift-package-index",
        "server",
        "web",
        "framework",
        "MIT",
        "package-popularity",
    ]
    assert first.credibility > 0.9
    assert first.metadata["package_ecosystem"] == "swift"
    assert first.metadata["registry"] == "swift_package_index"
    assert first.metadata["package_name"] == "Vapor"
    assert first.metadata["repository_url"] == "https://github.com/vapor/vapor"
    assert first.metadata["package_url"] == "https://swiftpackageindex.com/vapor/vapor"
    assert first.metadata["stars"] == 25_000
    assert first.metadata["score"] == 8.5
    assert first.metadata["latest_version"] == "4.100.0"
    assert first.metadata["search_query"] == "server"
    assert first.metadata["signal_role"] == "solution"


@pytest.mark.asyncio
async def test_swift_package_index_query_config_and_filters_are_used() -> None:
    adapter = SwiftPackageIndexAdapter(
        config={
            "queries": ["swift"],
            "max_results": 1,
            "keywords": ["server"],
            "categories": ["framework"],
        }
    )

    with patch("max.sources.swift_package_index.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "Vapor"
    assert mock_fetch.call_args.kwargs["params"] == {
        "query": "swift",
        "page": 1,
        "per_page": 1,
    }


@pytest.mark.asyncio
async def test_swift_package_index_handles_missing_optional_fields() -> None:
    adapter = SwiftPackageIndexAdapter(config={"queries": ["minimal"]})

    with patch("max.sources.swift_package_index.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_MISSING_OPTIONAL)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "MinimalPackage"
    assert signal.content == "MinimalPackage"
    assert signal.url == "https://swiftpackageindex.com/example/minimal-package"
    assert signal.published_at is None
    assert signal.credibility == 0.15
    assert signal.metadata["stars"] is None
    assert signal.metadata["score"] is None
    assert signal.metadata["latest_version"] is None
    assert signal.metadata["keywords"] == []
    assert signal.metadata["categories"] == []


@pytest.mark.asyncio
async def test_swift_package_index_http_errors_do_not_raise() -> None:
    adapter = SwiftPackageIndexAdapter(config={"queries": ["unavailable"]})

    with patch("max.sources.swift_package_index.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError(
            "swift_package_index",
            503,
            SWIFT_PACKAGE_INDEX_SEARCH,
        )

        signals = await adapter.fetch(limit=10)

    assert signals == []
