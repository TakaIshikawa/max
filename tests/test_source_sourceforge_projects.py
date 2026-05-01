"""Tests for the SourceForge projects source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError
from max.sources.sourceforge_projects import (
    SOURCEFORGE_PROJECTS_API,
    SourceForgeProjectsAdapter,
    _DEFAULT_QUERIES,
    _extract_projects,
    _parse_datetime,
)
from max.types.signal import SignalSourceType


SEARCH_RESPONSE = {
    "projects": [
        {
            "id": "sourceforge:keepass",
            "shortname": "keepass",
            "name": "KeePass Password Safe",
            "summary": "A lightweight and easy-to-use password manager.",
            "url": "https://sourceforge.net/projects/keepass/",
            "categories": [
                {"shortname": "security", "name": "Security"},
                "Password Managers",
            ],
            "tags": ["encryption", "desktop"],
            "license": {"name": "GNU General Public License version 2.0"},
            "downloads": 2_500_000,
            "weekly_downloads": 12_345,
            "rating": 4.8,
            "created_at": "2020-01-02T03:04:05Z",
            "updated_at": "2026-04-20T10:00:00Z",
            "repository": {"url": "https://git.code.sf.net/p/keepass/code"},
            "homepage": "https://keepass.info/",
            "maintainers": [{"username": "dominik"}],
        },
        {
            "shortname": "sevenzip",
            "name": "7-Zip",
            "description": "A file archiver with a high compression ratio.",
            "categories": ["Compression"],
            "tags": ["archive"],
            "downloads_total": 8_000_000,
            "creation_date": "2019-05-01T00:00:00+00:00",
        },
    ]
}

DIRECT_RESPONSE = {
    "project": {
        "short_name": "notepad-plus",
        "name": "Notepad++",
        "short_description": "Source code editor and Notepad replacement.",
        "category": "Text Editors",
        "labels": ["windows", "editor"],
        "licenses": ["GPL-3.0"],
        "downloads_month": 100_000,
        "modified": "2026-04-18T09:30:00Z",
    }
}


def test_sourceforge_projects_adapter_properties() -> None:
    adapter = SourceForgeProjectsAdapter()

    assert adapter.name == "sourceforge_projects"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.categories == []
    assert adapter.projects == []


def test_sourceforge_projects_config_normalization() -> None:
    adapter = SourceForgeProjectsAdapter(
        config={
            "queries": ["security"],
            "watchlist_terms": ["database"],
            "categories": [" development ", "development", "", 5],
            "project_names": [" keepass ", "/notepad-plus/", "keepass"],
        }
    )

    assert adapter.queries == ["security", "database"]
    assert adapter.categories == ["development"]
    assert adapter.projects == ["keepass", "notepad-plus"]


@pytest.mark.asyncio
async def test_fetch_emits_normalized_project_signals() -> None:
    adapter = SourceForgeProjectsAdapter(config={"queries": ["security"]})

    with patch("max.sources.sourceforge_projects.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.args[0] == SOURCEFORGE_PROJECTS_API
    assert mock_fetch.call_args.kwargs["params"] == {
        "q": "security",
        "limit": 10,
        "offset": 0,
    }

    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "sourceforge_projects"
    assert first.title == "KeePass Password Safe"
    assert first.content == "A lightweight and easy-to-use password manager."
    assert first.url == "https://sourceforge.net/projects/keepass/"
    assert first.author == "dominik"
    assert first.published_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert first.credibility > 0.9
    assert first.tags == ["security", "password-managers", "encryption", "desktop"]
    assert first.metadata["sourceforge_id"] == "sourceforge:keepass"
    assert first.metadata["shortname"] == "keepass"
    assert first.metadata["categories"] == ["security", "Password Managers"]
    assert first.metadata["tags"] == ["encryption", "desktop"]
    assert first.metadata["license"] == "GNU General Public License version 2.0"
    assert first.metadata["downloads"] == 2_500_000
    assert first.metadata["weekly_downloads"] == 12_345
    assert first.metadata["rating"] == 4.8
    assert first.metadata["repository"] == "https://git.code.sf.net/p/keepass/code"
    assert first.metadata["homepage"] == "https://keepass.info/"
    assert first.metadata["created_at"] == "2020-01-02T03:04:05+00:00"
    assert first.metadata["updated_at"] == "2026-04-20T10:00:00+00:00"
    assert first.metadata["search_query"] == "security"
    assert first.metadata["signal_role"] == "market"


@pytest.mark.asyncio
async def test_fetch_uses_categories_and_direct_project_lookup() -> None:
    adapter = SourceForgeProjectsAdapter(
        config={"queries": [], "categories": ["development"], "projects": ["notepad-plus"]}
    )

    with patch("max.sources.sourceforge_projects.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: {"results": []}),
            MagicMock(json=lambda: DIRECT_RESPONSE),
        ]

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args_list[0].args[0] == SOURCEFORGE_PROJECTS_API
    assert mock_fetch.call_args_list[0].kwargs["params"] == {
        "category": "development",
        "limit": 5,
        "offset": 0,
    }
    assert mock_fetch.call_args_list[1].args[0] == f"{SOURCEFORGE_PROJECTS_API}notepad-plus/"
    assert mock_fetch.call_args_list[1].kwargs["params"] == {}
    assert signals[0].title == "Notepad++"
    assert signals[0].content == "Source code editor and Notepad replacement."
    assert signals[0].url == "https://sourceforge.net/projects/notepad-plus/"
    assert signals[0].published_at == datetime(2026, 4, 18, 9, 30, tzinfo=timezone.utc)
    assert signals[0].tags == ["text-editors", "windows", "editor"]
    assert signals[0].metadata["project_name"] == "notepad-plus"
    assert signals[0].metadata["monthly_downloads"] == 100_000


@pytest.mark.asyncio
async def test_fetch_respects_limit_and_deduplicates_projects() -> None:
    adapter = SourceForgeProjectsAdapter(config={"queries": ["security", "password"]})
    first_response = {
        "projects": [
            {"shortname": "keepass", "name": "KeePass", "summary": "Password manager"},
            {"shortname": "sevenzip", "name": "7-Zip", "summary": "File archiver"},
        ]
    }
    second_response = {
        "projects": [
            {"shortname": "KEEPASS", "name": "Duplicate", "summary": "Duplicate"},
            {"shortname": "winscp", "name": "WinSCP", "summary": "File transfer"},
        ]
    }

    with patch("max.sources.sourceforge_projects.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: first_response),
            MagicMock(json=lambda: second_response),
        ]

        signals = await adapter.fetch(limit=3)

    assert [signal.metadata["shortname"] for signal in signals] == ["keepass", "sevenzip", "winscp"]
    assert mock_fetch.call_count == 2
    assert mock_fetch.call_args_list[0].kwargs["params"]["limit"] == 3
    assert mock_fetch.call_args_list[1].kwargs["params"]["limit"] == 1


@pytest.mark.asyncio
async def test_fetch_handles_empty_malformed_and_failed_responses() -> None:
    adapter = SourceForgeProjectsAdapter(
        config={"queries": ["empty", "broken", "failed", "network", "valid"]}
    )

    with patch("max.sources.sourceforge_projects.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: {"projects": []}),
            MagicMock(json=lambda: {"projects": [{"name": ""}, "bad", {"shortname": "valid"}]}),
            AdapterFetchError("sourceforge_projects", 500, SOURCEFORGE_PROJECTS_API),
            httpx.RequestError("network error"),
            MagicMock(json=lambda: {"projects": [{"shortname": "another", "summary": "Usable"}]}),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["valid", "another"]
    assert signals[0].content == "valid"
    assert mock_fetch.call_count == 5


@pytest.mark.asyncio
async def test_fetch_handles_invalid_json_without_raising() -> None:
    adapter = SourceForgeProjectsAdapter(config={"queries": ["invalid"]})

    with patch("max.sources.sourceforge_projects.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=MagicMock(side_effect=ValueError("invalid json")))

        signals = await adapter.fetch(limit=10)

    assert signals == []


def test_extract_projects_supports_common_response_shapes() -> None:
    project = {"shortname": "keepass"}

    assert _extract_projects({"projects": [project]}) == [project]
    assert _extract_projects({"results": [{"project": project}]}) == [project]
    assert _extract_projects([{"project_summary": project}]) == [project]
    assert _extract_projects({"items": ["bad", {"node": project}]}) == [project]
    assert _extract_projects({"unexpected": []}) == []
    assert _extract_projects("bad") == []


def test_parse_datetime_handles_invalid_and_naive_values() -> None:
    assert _parse_datetime("2026-04-01T12:00:00Z") == datetime(
        2026,
        4,
        1,
        12,
        tzinfo=timezone.utc,
    )
    assert _parse_datetime("2026-04-01T12:00:00") == datetime(
        2026,
        4,
        1,
        12,
        tzinfo=timezone.utc,
    )
    assert _parse_datetime("not a date") is None
    assert _parse_datetime(None) is None


def test_sourceforge_projects_registry_discovery() -> None:
    from max.sources.registry import get_adapter, get_adapter_metadata, reload_registry

    reload_registry()
    adapter = get_adapter("sourceforge_projects")
    metadata = get_adapter_metadata()["sourceforge_projects"]

    assert isinstance(adapter, SourceForgeProjectsAdapter)
    assert metadata.config_keys == ["queries", "categories", "projects", "project_names"]
    assert "SourceForge projects" in metadata.description
