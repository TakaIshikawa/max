"""Tests for the crates.io download trends source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.crates_download_trends import CratesDownloadTrendsAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: object, *, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _mock_client(request):
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(side_effect=request)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


@pytest.mark.asyncio
async def test_fetch_configured_crates_as_market_signals() -> None:
    adapter = CratesDownloadTrendsAdapter(
        config={"crates": ["Serde", "tokio"], "window_days": 4}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/serde/downloads"):
            return _response(
                {
                    "version_downloads": [
                        {"date": "2026-04-19", "downloads": 90, "version": 1},
                        {"date": "2026-04-20", "downloads": 100, "version": 1},
                        {"date": "2026-04-21", "downloads": 120, "version": 1},
                        {"date": "2026-04-21", "downloads": 30, "version": 2},
                        {"date": "2026-04-22", "downloads": 180, "version": 1},
                    ]
                }
            )
        if url.endswith("/tokio/downloads"):
            return _response(
                {
                    "crate": "tokio",
                    "version_downloads": [
                        {"date": "2026-04-20", "downloads": 200},
                        {"date": "2026-04-21", "downloads": 200},
                        {"date": "2026-04-22", "downloads": 200},
                        {"date": "2026-04-23", "downloads": 200},
                    ],
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.crates_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["crate_name"] for signal in signals] == ["serde", "tokio"]
    assert all(signal.source_adapter == "crates_download_trends" for signal in signals)
    assert all(signal.source_type == SignalSourceType.MARKET for signal in signals)

    first = signals[0]
    assert first.id == "crates_download_trends:serde:2026-04-19:2026-04-22"
    assert first.title == "serde crates.io download trend"
    assert first.url == "https://crates.io/crates/serde"
    assert first.published_at == datetime(2026, 4, 22, tzinfo=timezone.utc)
    assert first.metadata["package_ecosystem"] == "crates.io"
    assert first.metadata["package_name"] == "serde"
    assert first.metadata["time_window_days"] == 4
    assert first.metadata["time_window_start"] == "2026-04-19"
    assert first.metadata["time_window_end"] == "2026-04-22"
    assert first.metadata["downloads"] == 520
    assert first.metadata["download_total"] == 520
    assert first.metadata["previous_window_downloads"] == 190
    assert first.metadata["current_window_downloads"] == 330
    assert first.metadata["trend_direction"] == "improving"
    assert first.metadata["trend_points"] == [
        {"date": "2026-04-19", "downloads": 90},
        {"date": "2026-04-20", "downloads": 100},
        {"date": "2026-04-21", "downloads": 150},
        {"date": "2026-04-22", "downloads": 180},
    ]
    assert first.metadata["api_url"] == "https://crates.io/api/v1/crates/serde/downloads"
    assert first.metadata["signal_role"] == "market"
    assert {"rust", "crates.io", "crate", "downloads", "improving", "serde"} <= set(first.tags)

    second = signals[1]
    assert second.metadata["trend_direction"] == "stable"
    assert second.metadata["downloads"] == 800


@pytest.mark.asyncio
async def test_packages_alias_min_downloads_and_max_items_are_used() -> None:
    adapter = CratesDownloadTrendsAdapter(
        config={
            "packages": ["small-crate", "popular-crate", "ignored"],
            "min_downloads": 100,
            "max_items": 1,
        }
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        if url.endswith("/small-crate/downloads"):
            return _response({"version_downloads": [{"date": "2026-04-22", "downloads": 99}]})
        if url.endswith("/popular-crate/downloads"):
            return _response({"version_downloads": [{"date": "2026-04-22", "downloads": 100}]})
        if url.endswith("/ignored/downloads"):
            return _response({"version_downloads": [{"date": "2026-04-22", "downloads": 200}]})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.crates_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["crate_name"] == "popular-crate"
    assert urls == [
        "https://crates.io/api/v1/crates/small-crate/downloads",
        "https://crates.io/api/v1/crates/popular-crate/downloads",
    ]


@pytest.mark.asyncio
async def test_declining_trend_is_reported_from_recent_window() -> None:
    adapter = CratesDownloadTrendsAdapter(config={"crates": ["cool-lib"], "window_days": 4})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/cool-lib/downloads"):
            return _response(
                {
                    "download_history": [
                        {"date": "2026-04-18", "downloads": 999},
                        {"date": "2026-04-19", "downloads": 500},
                        {"date": "2026-04-20", "downloads": 500},
                        {"date": "2026-04-21", "downloads": 200},
                        {"date": "2026-04-22", "downloads": 200},
                    ]
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.crates_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "crates_download_trends:cool-lib:2026-04-19:2026-04-22"
    assert signals[0].metadata["downloads"] == 1_400
    assert signals[0].metadata["previous_window_downloads"] == 1_000
    assert signals[0].metadata["current_window_downloads"] == 400
    assert signals[0].metadata["trend_direction"] == "declining"


@pytest.mark.asyncio
async def test_malformed_responses_are_skipped_without_failing_fetch() -> None:
    adapter = CratesDownloadTrendsAdapter(
        config={"crates": ["not-object", "missing-history", "bad-row", "valid"]}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/not-object/downloads"):
            return _response([{"date": "2026-04-22", "downloads": 10}])
        if url.endswith("/missing-history/downloads"):
            return _response({"meta": {"extra_downloads": 10}})
        if url.endswith("/bad-row/downloads"):
            return _response({"version_downloads": [{"date": "nope", "downloads": "bad"}]})
        if url.endswith("/valid/downloads"):
            return _response({"version_downloads": [{"date": "2026-04-22", "downloads": 22_000}]})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.crates_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["crate_name"] == "valid"
    assert signals[0].metadata["downloads"] == 22_000


@pytest.mark.asyncio
async def test_api_error_does_not_fail_whole_fetch() -> None:
    adapter = CratesDownloadTrendsAdapter(config={"crates": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/unavailable/downloads"):
            return _response({}, status_code=503)
        if url.endswith("/available/downloads"):
            return _response({"version_downloads": [{"date": "2026-04-22", "downloads": 55_000}]})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.crates_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["crate_name"] == "available"
