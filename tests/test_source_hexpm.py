"""Tests for the Hex.pm source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.base import AdapterFetchError
from max.sources.hexpm import HEXPM_API_BASE_URL, HexPmAdapter
from max.types.signal import SignalSourceType


MOCK_PACKAGE = {
    "name": "oban",
    "latest_version": "2.19.4",
    "latest_stable_version": "2.19.4",
    "downloads": {
        "all": 72_000_000,
        "recent": 1_250_000,
        "day": 42_000,
        "week": 290_000,
    },
    "updated_at": "2026-04-20T12:30:00.000Z",
    "meta": {
        "description": "Robust job processing, backed by modern PostgreSQL.",
        "licenses": ["Apache-2.0"],
        "links": {
            "GitHub": "https://github.com/sorentwo/oban",
            "Docs": "https://hexdocs.pm/oban",
        },
    },
}


def test_hexpm_adapter_properties_and_config() -> None:
    adapter = HexPmAdapter(
        config={
            "packages": ["Oban", " phoenix "],
            "watchlist_terms": ["ecto"],
            "max_results": 2,
            "api_base_url": "https://hex.example/api/",
        }
    )

    assert adapter.name == "hexpm"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.packages == ["Oban", "phoenix", "ecto"]
    assert adapter.max_results == 2
    assert adapter.api_base_url == "https://hex.example/api"


@pytest.mark.asyncio
async def test_hexpm_adapter_fetches_and_normalizes_package_metadata() -> None:
    adapter = HexPmAdapter(config={"packages": ["Oban"], "api_base_url": "https://hex.example/api"})

    with patch("max.sources.hexpm.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_PACKAGE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args.args[0] == "https://hex.example/api/packages/oban"
    assert mock_fetch.call_args.kwargs["headers"] == {"User-Agent": "max-hexpm-adapter/0.1"}

    signal = signals[0]
    assert signal.id == "hexpm:oban:2.19.4"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "hexpm"
    assert signal.title == "oban@2.19.4"
    assert signal.content == (
        "Robust job processing, backed by modern PostgreSQL. "
        "Hex.pm reports 72,000,000 total downloads and 1,250,000 recent downloads for oban."
    )
    assert signal.url == "https://github.com/sorentwo/oban"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == [
        "elixir",
        "erlang",
        "beam",
        "hexpm",
        "package",
        "downloads",
        "Apache-2.0",
        "oban",
        "open-source",
    ]
    assert signal.credibility > 0.8
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["package_ecosystem"] == "hexpm"
    assert signal.metadata["package_name"] == "oban"
    assert signal.metadata["hexpm_name"] == "oban"
    assert signal.metadata["latest_version"] == "2.19.4"
    assert signal.metadata["latest_stable_version"] == "2.19.4"
    assert signal.metadata["downloads"] == 72_000_000
    assert signal.metadata["download_count"] == 72_000_000
    assert signal.metadata["recent_downloads"] == 1_250_000
    assert signal.metadata["daily_downloads"] == 42_000
    assert signal.metadata["weekly_downloads"] == 290_000
    assert signal.metadata["repository_url"] == "https://github.com/sorentwo/oban"
    assert signal.metadata["links"]["Docs"] == "https://hexdocs.pm/oban"
    assert signal.metadata["updated_at"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["package_url"] == "https://hex.pm/packages/oban"
    assert signal.metadata["api_url"] == "https://hex.example/api/packages/oban"


@pytest.mark.asyncio
async def test_hexpm_adapter_handles_missing_optional_fields() -> None:
    adapter = HexPmAdapter(config={"packages": ["minimal"]})

    with patch("max.sources.hexpm.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: {"name": "minimal"})

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "hexpm:minimal:unknown"
    assert signal.title == "minimal"
    assert signal.content == "minimal"
    assert signal.url == "https://hex.pm/packages/minimal"
    assert signal.published_at is None
    assert signal.credibility == 0.15
    assert signal.metadata["downloads"] == 0
    assert signal.metadata["recent_downloads"] == 0
    assert signal.metadata["latest_version"] is None
    assert signal.metadata["repository_url"] is None
    assert signal.metadata["links"] == {}


@pytest.mark.asyncio
async def test_hexpm_adapter_empty_package_config_returns_no_signals() -> None:
    adapter = HexPmAdapter()

    with patch("max.sources.hexpm.fetch_with_retry") as mock_fetch:
        signals = await adapter.fetch(limit=10)

    assert signals == []
    mock_fetch.assert_not_called()


@pytest.mark.asyncio
async def test_hexpm_adapter_skips_http_failures_and_malformed_records(caplog) -> None:
    adapter = HexPmAdapter(config={"packages": ["broken", "malformed", "valid"]})

    with patch("max.sources.hexpm.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            AdapterFetchError("hexpm", 500, f"{HEXPM_API_BASE_URL}/packages/broken"),
            MagicMock(json=lambda: ["not", "a", "dict"]),
            MagicMock(json=lambda: {**MOCK_PACKAGE, "name": "valid"}),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "valid"
    assert "failed to fetch Hex.pm package broken" in caplog.text
    assert "malformed package record for malformed" in caplog.text


@pytest.mark.asyncio
async def test_hexpm_adapter_respects_max_results() -> None:
    adapter = HexPmAdapter(config={"packages": ["oban", "phoenix"], "max_results": 1})

    with patch("max.sources.hexpm.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_PACKAGE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
