"""Tests for the Packagist source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.packagist import PackagistAdapter, _DEFAULT_QUERIES
from max.sources.registry import get_adapter, get_adapter_metadata, list_adapters, reload_registry
from max.types.signal import SignalSourceType


MOCK_SEARCH = {
    "results": [
        {
            "name": "laravel/framework",
            "description": "The Laravel Framework.",
            "url": "https://packagist.org/packages/laravel/framework",
            "repository": "https://github.com/laravel/framework",
            "downloads": {"total": 420_000_000, "monthly": 9_500_000, "daily": 320_000},
            "favers": 82_000,
            "github_stars": 34_000,
        }
    ],
    "total": 1,
}

MOCK_DETAILS = {
    "packages": {
        "laravel/framework": [
            {
                "name": "laravel/framework",
                "version": "v11.0.0",
                "version_normalized": "11.0.0.0",
                "description": "Old Laravel release.",
                "time": "2025-01-01T10:00:00+00:00",
                "type": "library",
                "license": ["MIT"],
                "keywords": ["framework", "laravel"],
                "authors": [{"name": "Taylor Otwell"}],
                "source": {"url": "https://github.com/laravel/framework"},
            },
            {
                "name": "laravel/framework",
                "version": "v12.1.0",
                "version_normalized": "12.1.0.0",
                "description": "The Laravel Framework.",
                "time": "2026-04-20T12:30:00+00:00",
                "type": "library",
                "license": ["MIT"],
                "keywords": ["framework", "laravel"],
                "authors": [{"name": "Taylor Otwell"}],
                "source": {"url": "https://github.com/laravel/framework"},
                "support": {"issues": "https://github.com/laravel/framework/issues"},
            },
        ]
    }
}


def test_packagist_adapter_properties() -> None:
    adapter = PackagistAdapter()

    assert adapter.name == "packagist"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.include_maintenance is True
    assert adapter.active_release_days == 365


def test_packagist_adapter_custom_config() -> None:
    adapter = PackagistAdapter(
        config={
            "queries": ["symfony"],
            "watchlist_terms": ["wordpress"],
            "include_maintenance": False,
            "active_release_days": 90,
        }
    )

    assert adapter.queries == ["symfony", "wordpress"]
    assert adapter.include_maintenance is False
    assert adapter.active_release_days == 90


@pytest.mark.asyncio
async def test_packagist_adapter_fetches_search_details_and_maintenance_signals() -> None:
    adapter = PackagistAdapter(config={"queries": ["laravel"]})

    with patch("max.sources.packagist.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(json=lambda: MOCK_DETAILS),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args_list[0].args[0] == "https://packagist.org/search.json"
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"q": "laravel", "per_page": 10}
    assert mock_fetch.call_args_list[1].args[0] == (
        "https://repo.packagist.org/p2/laravel/framework.json"
    )

    package = signals[0]
    assert package.id == "packagist:laravel/framework:v12.1.0:package"
    assert package.source_type == SignalSourceType.REGISTRY
    assert package.source_adapter == "packagist"
    assert package.title == "laravel/framework@v12.1.0"
    assert package.content == "The Laravel Framework."
    assert package.url == "https://packagist.org/packages/laravel/framework"
    assert package.author == "Taylor Otwell"
    assert package.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert package.tags == [
        "php",
        "packagist",
        "laravel",
        "framework",
        "MIT",
        "package-popularity",
        "repository-metadata",
        "maintained",
    ]
    assert package.credibility > 0.8
    assert package.metadata["package_ecosystem"] == "packagist"
    assert package.metadata["package_name"] == "laravel/framework"
    assert package.metadata["latest_version"] == "v12.1.0"
    assert package.metadata["downloads"] == 420_000_000
    assert package.metadata["monthly_downloads"] == 9_500_000
    assert package.metadata["repository_url"] == "https://github.com/laravel/framework"
    assert package.metadata["stars"] == 34_000
    assert package.metadata["search_query"] == "laravel"
    assert package.metadata["signal_kind"] == "package_metadata"
    assert package.metadata["maintained"] is True

    maintenance = signals[1]
    assert maintenance.source_type == SignalSourceType.TRENDING
    assert maintenance.source_adapter == "packagist"
    assert maintenance.title == "laravel/framework maintenance activity"
    assert maintenance.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert maintenance.tags == ["php", "packagist", "laravel", "maintenance", "release-activity"]
    assert maintenance.credibility >= package.credibility
    assert maintenance.metadata["signal_kind"] == "maintenance_activity"
    assert maintenance.metadata["latest_version"] == "v12.1.0"


@pytest.mark.asyncio
async def test_packagist_adapter_empty_results() -> None:
    adapter = PackagistAdapter(config={"queries": ["missing"]})

    with patch("max.sources.packagist.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"results": [], "total": 0})

        signals = await adapter.fetch(limit=10)

    assert signals == []
    assert mock_fetch.call_count == 1


@pytest.mark.asyncio
async def test_packagist_adapter_api_retry_failures_are_skipped() -> None:
    adapter = PackagistAdapter(config={"queries": ["laravel"]})

    with patch("max.sources.packagist.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = AdapterFetchError(
            "packagist",
            503,
            "https://packagist.org/search.json",
        )

        signals = await adapter.fetch(limit=10)

    assert signals == []
    assert mock_fetch.call_count == 1


def test_packagist_adapter_registry_discovery() -> None:
    reload_registry()

    try:
        assert "packagist" in list_adapters()
        adapter = get_adapter("packagist")
        assert isinstance(adapter, PackagistAdapter)

        metadata = get_adapter_metadata()["packagist"]
        assert metadata.config_keys == ["queries", "include_maintenance", "active_release_days"]
        assert metadata.required_keys == []
        assert "Packagist" in metadata.description
    finally:
        reload_registry()
