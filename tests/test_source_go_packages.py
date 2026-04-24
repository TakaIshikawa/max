"""Tests for the Go packages source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from max.sources.go_packages import GoPackagesAdapter, PKG_GO_DEV_SEARCH, _DEFAULT_QUERIES
from max.types.signal import SignalSourceType


MOCK_SEARCH = {
    "results": [
        {
            "module_path": "github.com/stretchr/testify",
            "synopsis": "A toolkit with common assertions and mocks.",
            "imported_by_count": 35_000,
            "version": "v1.10.0",
            "package_url": "https://pkg.go.dev/github.com/stretchr/testify",
            "tags": ["testing"],
        },
        {
            "module_path": "golang.org/x/sync",
            "synopsis": "Additional concurrency primitives.",
            "imported_by_count": "12,500",
            "version": "v0.12.0",
        },
        {
            "module_path": "net/http",
            "synopsis": "HTTP client and server implementations.",
            "imported_by_count": 100_000,
        },
        {
            "module_path": "example.com/tiny",
            "synopsis": "Small package.",
            "imported_by_count": 3,
        },
    ]
}


def test_go_packages_adapter_properties() -> None:
    adapter = GoPackagesAdapter()

    assert adapter.name == "go_packages"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.max_results == 10
    assert adapter.min_imported_by == 0
    assert adapter.include_stdlib is False


def test_go_packages_adapter_custom_config_and_watchlist() -> None:
    adapter = GoPackagesAdapter(
        config={
            "queries": ["testing"],
            "watchlist_terms": ["observability"],
            "max_results": 5,
            "min_imported_by": 100,
            "include_stdlib": True,
        }
    )

    assert adapter.queries == ["testing", "observability"]
    assert adapter.max_results == 5
    assert adapter.min_imported_by == 100
    assert adapter.include_stdlib is True


@pytest.mark.asyncio
async def test_go_packages_fetch_emits_normalized_signals() -> None:
    adapter = GoPackagesAdapter(config={"queries": ["testing"], "max_results": 5})

    with patch("max.sources.go_packages.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            json=lambda: MOCK_SEARCH,
        )

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 3
    assert mock_fetch.call_args.args[0] == PKG_GO_DEV_SEARCH
    assert mock_fetch.call_args.kwargs["params"] == {"q": "testing", "limit": 5}

    first = signals[0]
    assert first.id.startswith("go_packages:")
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "go_packages"
    assert first.title == "github.com/stretchr/testify@v1.10.0"
    assert first.content == "A toolkit with common assertions and mocks."
    assert first.url == "https://pkg.go.dev/github.com/stretchr/testify"
    assert first.tags == ["go", "golang", "testing", "package-popularity"]
    assert first.credibility > 0.9
    assert first.metadata["package_ecosystem"] == "go"
    assert first.metadata["module_path"] == "github.com/stretchr/testify"
    assert first.metadata["synopsis"] == "A toolkit with common assertions and mocks."
    assert first.metadata["imported_by_count"] == 35_000
    assert first.metadata["version"] == "v1.10.0"
    assert first.metadata["package_url"] == "https://pkg.go.dev/github.com/stretchr/testify"
    assert first.metadata["search_query"] == "testing"
    assert first.metadata["query"] == "testing"


@pytest.mark.asyncio
async def test_go_packages_honors_filters_and_limit() -> None:
    adapter = GoPackagesAdapter(
        config={
            "queries": ["testing"],
            "max_results": 2,
            "min_imported_by": 10_000,
            "include_stdlib": False,
        }
    )

    with patch("max.sources.go_packages.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            json=lambda: MOCK_SEARCH,
        )

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["module_path"] == "github.com/stretchr/testify"
    assert mock_fetch.call_args.kwargs["params"] == {"q": "testing", "limit": 1}


@pytest.mark.asyncio
async def test_go_packages_honors_max_results_per_query() -> None:
    adapter = GoPackagesAdapter(
        config={"queries": ["testing"], "max_results": 2, "include_stdlib": True}
    )

    with patch("max.sources.go_packages.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            json=lambda: MOCK_SEARCH,
        )

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["module_path"] for signal in signals] == [
        "github.com/stretchr/testify",
        "golang.org/x/sync",
    ]
    assert mock_fetch.call_args.kwargs["params"] == {"q": "testing", "limit": 2}


@pytest.mark.asyncio
async def test_go_packages_can_include_stdlib() -> None:
    adapter = GoPackagesAdapter(
        config={"queries": ["http"], "min_imported_by": 90_000, "include_stdlib": True}
    )

    with patch("max.sources.go_packages.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            json=lambda: MOCK_SEARCH,
        )

        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["module_path"] for signal in signals] == ["net/http"]


@pytest.mark.asyncio
async def test_go_packages_signal_ids_are_deterministic() -> None:
    adapter = GoPackagesAdapter(config={"queries": ["testing"]})

    with patch("max.sources.go_packages.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(
            headers={"content-type": "application/json"},
            json=lambda: MOCK_SEARCH,
        )
        first = await adapter.fetch(limit=10)
        second = await adapter.fetch(limit=10)

    assert [signal.id for signal in first] == [signal.id for signal in second]
