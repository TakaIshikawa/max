"""Tests for the NuGet source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.nuget import NuGetAdapter, _DEFAULT_PACKAGE_NAMES, _DEFAULT_QUERIES
from max.types.signal import SignalSourceType


MOCK_REGISTRATION = {
    "items": [
        {
            "items": [
                {
                    "@id": "https://api.nuget.org/v3/registration5-gz-semver2/test.package/1.0.0.json",
                    "packageContent": "https://api.nuget.org/v3-flatcontainer/test.package/1.0.0/test.package.1.0.0.nupkg",
                    "catalogEntry": {
                        "id": "Test.Package",
                        "version": "1.0.0",
                        "description": "Old release",
                        "authors": "test-author",
                        "published": "2026-02-01T10:00:00Z",
                        "projectUrl": "https://example.com/test",
                        "tags": ["ai", "dotnet"],
                    },
                },
                {
                    "@id": "https://api.nuget.org/v3/registration5-gz-semver2/test.package/1.1.0.json",
                    "packageContent": "https://api.nuget.org/v3-flatcontainer/test.package/1.1.0/test.package.1.1.0.nupkg",
                    "catalogEntry": {
                        "id": "Test.Package",
                        "version": "1.1.0",
                        "description": "Recent release",
                        "authors": "test-author",
                        "published": "2026-04-20T12:30:00Z",
                        "projectUrl": "https://example.com/test",
                        "tags": ["ai", "dotnet"],
                    },
                },
            ]
        }
    ]
}

MOCK_SEARCH = {
    "data": [
        {
            "id": "Search.Package",
            "version": "2.0.0",
            "description": "Search result package",
            "authors": "search-author",
            "totalDownloads": 12345,
            "verified": True,
            "projectUrl": "https://example.com/search",
            "tags": ["mcp", "agent"],
            "versions": [{"version": "2.0.0", "downloads": 500}],
        }
    ]
}


def test_nuget_adapter_properties() -> None:
    adapter = NuGetAdapter()

    assert adapter.name == "nuget"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.package_names == _DEFAULT_PACKAGE_NAMES
    assert adapter.include_prerelease is False


def test_nuget_adapter_custom_config() -> None:
    adapter = NuGetAdapter(
        config={
            "queries": ["semantic kernel"],
            "package_names": ["Microsoft.SemanticKernel"],
            "watchlist_terms": ["mcp"],
            "include_prerelease": True,
        }
    )

    assert adapter.queries == ["semantic kernel", "mcp"]
    assert adapter.package_names == ["Microsoft.SemanticKernel", "mcp"]
    assert adapter.include_prerelease is True


@pytest.mark.asyncio
async def test_nuget_adapter_fetches_exact_package_activity() -> None:
    adapter = NuGetAdapter(config={"queries": [], "package_names": ["Test.Package"]})

    with patch("max.sources.nuget.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_REGISTRATION)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert "registration5-gz-semver2/test.package/index.json" in mock_fetch.call_args.args[0]

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "nuget"
    assert signal.title == "Test.Package@1.1.0"
    assert signal.content == "Recent release"
    assert signal.url == "https://www.nuget.org/packages/Test.Package/1.1.0"
    assert signal.author == "test-author"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == ["ai", "dotnet"]
    assert signal.metadata["package_id"] == "Test.Package"
    assert signal.metadata["package_ecosystem"] == "nuget"
    assert signal.metadata["version"] == "1.1.0"
    assert signal.metadata["downloads"] == 0
    assert signal.metadata["download_count"] == 0
    assert signal.metadata["publish_date"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["project_url"] == "https://example.com/test"
    assert signal.metadata["evidence_url"] == "https://www.nuget.org/packages/Test.Package/1.1.0"
    assert signal.metadata["package_name"] == "Test.Package"


@pytest.mark.asyncio
async def test_nuget_adapter_fetches_search_results_with_registration_details() -> None:
    adapter = NuGetAdapter(config={"queries": ["mcp"], "package_names": []})

    with patch("max.sources.nuget.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(json=lambda: MOCK_REGISTRATION),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args_list[0].kwargs["params"] == {
        "q": "mcp",
        "take": 10,
        "prerelease": "false",
    }
    assert signals[0].title == "Test.Package@1.1.0"
    assert signals[0].metadata["downloads"] == 12345
    assert signals[0].metadata["version_downloads"] is None
    assert signals[0].metadata["search_query"] == "mcp"
    assert signals[0].metadata["verified"] is True


@pytest.mark.asyncio
async def test_nuget_adapter_falls_back_to_search_metadata_when_registration_fails() -> None:
    adapter = NuGetAdapter(config={"queries": ["mcp"], "package_names": []})

    with patch("max.sources.nuget.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(status_code=404, json=lambda: {}),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Search.Package@2.0.0"
    assert signal.published_at is None
    assert signal.tags == ["mcp", "agent"]
    assert signal.metadata["downloads"] == 12345
    assert signal.metadata["version_downloads"] == 500
    assert signal.metadata["project_url"] == "https://example.com/search"


@pytest.mark.asyncio
async def test_nuget_adapter_respects_limit_and_dedupes_packages() -> None:
    adapter = NuGetAdapter(config={"queries": ["mcp"], "package_names": ["Test.Package"]})

    with patch("max.sources.nuget.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_REGISTRATION)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["package_id"] == "Test.Package"
    assert mock_fetch.call_count == 1
