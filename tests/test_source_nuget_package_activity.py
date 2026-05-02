"""Tests for the NuGet package activity source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.nuget_package_activity import (
    NuGetPackageActivityAdapter,
    parse_package_signal,
)
from max.types.signal import SignalSourceType


MOCK_REGISTRATION = {
    "items": [
        {
            "items": [
                {
                    "@id": "https://api.nuget.org/v3/registration5-gz-semver2/example.package/1.0.0.json",
                    "packageContent": "https://api.nuget.org/v3-flatcontainer/example.package/1.0.0/example.package.1.0.0.nupkg",
                    "catalogEntry": {
                        "id": "Example.Package",
                        "version": "1.0.0",
                        "description": "Old release",
                        "authors": "example-author",
                        "published": "2026-01-01T10:00:00Z",
                        "projectUrl": "https://example.com/package",
                        "tags": ["ai", "dotnet"],
                    },
                },
                {
                    "@id": "https://api.nuget.org/v3/registration5-gz-semver2/example.package/1.2.0.json",
                    "packageContent": "https://api.nuget.org/v3-flatcontainer/example.package/1.2.0/example.package.1.2.0.nupkg",
                    "catalogEntry": {
                        "id": "Example.Package",
                        "version": "1.2.0",
                        "description": "Current release",
                        "authors": "example-author",
                        "published": "2026-04-20T12:30:00Z",
                        "projectUrl": "https://example.com/package",
                        "tags": ["ai", "dotnet", "agent"],
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
            "owners": ["search-owner"],
            "totalDownloads": 12_345,
            "verified": True,
            "projectUrl": "https://example.com/search",
            "tags": ["mcp", "agent"],
            "versions": [{"version": "2.0.0", "downloads": 500}],
        }
    ]
}


def test_parse_package_signal_preserves_activity_metadata() -> None:
    signal = parse_package_signal(MOCK_SEARCH["data"][0], search_query="mcp")

    assert signal is not None
    assert signal.id == "nuget_package_activity:Search.Package:2.0.0"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "nuget_package_activity"
    assert signal.title == "Search.Package@2.0.0"
    assert signal.url == "https://www.nuget.org/packages/Search.Package/2.0.0"
    assert signal.author == "search-author"
    assert signal.published_at is None
    assert "12,345 total downloads" in signal.content
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["package_ecosystem"] == "nuget"
    assert signal.metadata["package_id"] == "Search.Package"
    assert signal.metadata["version"] == "2.0.0"
    assert signal.metadata["downloads"] == 12_345
    assert signal.metadata["download_count"] == 12_345
    assert signal.metadata["version_downloads"] == 500
    assert signal.metadata["description"] == "Search result package"
    assert signal.metadata["project_url"] == "https://example.com/search"
    assert signal.metadata["verified"] is True
    assert "nuget" in signal.tags
    assert "dotnet" in signal.tags
    assert "mcp" in signal.tags


def test_parse_package_signal_handles_malformed_package_entry() -> None:
    assert parse_package_signal({"version": "1.0.0"}) is None


@pytest.mark.asyncio
async def test_fetch_uses_configured_packages_and_search_api() -> None:
    adapter = NuGetPackageActivityAdapter(
        config={
            "packages": ["Example.Package"],
            "queries": ["mcp"],
            "max_results_per_query": 3,
            "search_url": "https://nuget.test/query",
            "registration_url": "https://nuget.test/registration/{package_id}/index.json",
            "timeout": 8,
        }
    )

    with patch("max.sources.nuget_package_activity.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_REGISTRATION),
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(json=lambda: {"items": []}),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args_list[0].args[0] == "https://nuget.test/registration/example.package/index.json"
    assert mock_fetch.call_args_list[1].args[0] == "https://nuget.test/query"
    assert mock_fetch.call_args_list[1].kwargs["params"] == {
        "q": "mcp",
        "take": 3,
        "prerelease": "false",
    }
    assert [signal.id for signal in signals] == [
        "nuget_package_activity:Example.Package:1.2.0",
        "nuget_package_activity:Search.Package:2.0.0",
    ]

    first = signals[0]
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.metadata["registration_url"].endswith("/example.package/1.2.0.json")
    assert first.metadata["package_content_url"].endswith("example.package.1.2.0.nupkg")
    assert first.metadata["description"] == "Current release"
    assert first.metadata["project_url"] == "https://example.com/package"
    assert first.metadata["search_query"] is None

    second = signals[1]
    assert second.metadata["search_query"] == "mcp"
    assert second.metadata["downloads"] == 12_345


@pytest.mark.asyncio
async def test_fetch_handles_empty_and_malformed_api_payloads_without_crashing() -> None:
    adapter = NuGetPackageActivityAdapter(
        config={
            "packages": ["Malformed.Package", "Empty.Package"],
            "queries": ["bad"],
            "search_url": "https://nuget.test/query",
            "registration_url": "https://nuget.test/registration/{package_id}/index.json",
        }
    )

    with patch("max.sources.nuget_package_activity.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: {"items": [{"items": [{"catalogEntry": "not-a-dict"}]}]}),
            MagicMock(json=lambda: {"items": []}),
            MagicMock(json=lambda: {"data": [{"version": "1.0.0"}, "not-a-dict"]}),
        ]

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = NuGetPackageActivityAdapter(
        config={
            "packages": ["Example.Package"],
            "queries": ["mcp"],
            "registration_url": "https://nuget.test/registration/{package_id}/index.json",
        }
    )

    with patch("max.sources.nuget_package_activity.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_REGISTRATION)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
