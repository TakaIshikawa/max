"""Tests for npm downloads time-series adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.npm_downloads_adapter import (
    NpmDownloadsAdapter,
    _calculate_growth_rate,
    _moving_average,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_DOWNLOADS_RESPONSE = {
    "package": "react",
    "start": "2026-04-01",
    "end": "2026-04-07",
    "downloads": [
        {"day": "2026-04-01", "downloads": 1000},
        {"day": "2026-04-02", "downloads": 1200},
        {"day": "2026-04-03", "downloads": 1100},
        {"day": "2026-04-04", "downloads": 1300},
        {"day": "2026-04-05", "downloads": 800},
        {"day": "2026-04-06", "downloads": 600},
        {"day": "2026-04-07", "downloads": 1500},
    ],
}

MOCK_EMPTY_RESPONSE = {
    "package": "nonexistent-pkg",
    "start": "2026-04-01",
    "end": "2026-04-07",
    "downloads": [],
}


def _mock_response(payload, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_calculate_growth_rate_positive() -> None:
    # First half avg: 100, second half avg: 200 → 100% growth
    values = [100, 100, 200, 200]
    rate = _calculate_growth_rate(values)
    assert rate == 100.0


def test_calculate_growth_rate_negative() -> None:
    values = [200, 200, 100, 100]
    rate = _calculate_growth_rate(values)
    assert rate == -50.0


def test_calculate_growth_rate_zero_start() -> None:
    values = [0, 0, 100, 100]
    rate = _calculate_growth_rate(values)
    assert rate == 0.0


def test_calculate_growth_rate_single_value() -> None:
    assert _calculate_growth_rate([100]) == 0.0


def test_calculate_growth_rate_empty() -> None:
    assert _calculate_growth_rate([]) == 0.0


def test_moving_average_basic() -> None:
    values = [10, 20, 30, 40, 50, 60, 70]
    ma = _moving_average(values, window=7)
    assert len(ma) == 1
    assert ma[0] == pytest.approx(40.0)


def test_moving_average_multiple_windows() -> None:
    values = [10, 20, 30, 40, 50, 60, 70, 80]
    ma = _moving_average(values, window=7)
    assert len(ma) == 2


def test_moving_average_short_series() -> None:
    values = [10, 20, 30]
    ma = _moving_average(values, window=7)
    assert len(ma) == 1
    assert ma[0] == pytest.approx(20.0)


def test_moving_average_empty() -> None:
    assert _moving_average([], window=7) == []


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = NpmDownloadsAdapter()
    assert adapter.name == "npm_downloads_import"


def test_adapter_source_type() -> None:
    adapter = NpmDownloadsAdapter()
    assert adapter.source_type == SignalSourceType.REGISTRY.value


def test_adapter_default_packages() -> None:
    adapter = NpmDownloadsAdapter()
    assert "react" in adapter.packages


def test_adapter_custom_packages() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["lodash", "express"]})
    assert adapter.packages == ["lodash", "express"]


def test_adapter_range_days_default() -> None:
    adapter = NpmDownloadsAdapter()
    assert adapter.range_days == 30


def test_adapter_range_days_custom() -> None:
    adapter = NpmDownloadsAdapter(config={"range_days": 7})
    assert adapter.range_days == 7


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_downloads() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["react"]})

    with patch(
        "max.imports.npm_downloads_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_DOWNLOADS_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.title == "react"
    assert sig.source_adapter == "npm_downloads_import"
    assert sig.source_type == SignalSourceType.REGISTRY
    assert sig.metadata["total_downloads"] == 7500
    assert sig.metadata["days_counted"] == 7
    assert sig.metadata["peak_downloads"] == 1500
    assert sig.metadata["min_downloads"] == 600
    assert sig.metadata["growth_rate_pct"] != 0
    assert len(sig.metadata["moving_average_7d"]) == 1


@pytest.mark.asyncio
async def test_fetch_multiple_packages() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["react", "vue"]})

    with patch(
        "max.imports.npm_downloads_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_DOWNLOADS_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["react", "vue", "angular"]})

    with patch(
        "max.imports.npm_downloads_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_DOWNLOADS_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["nonexistent"]})

    with patch(
        "max.imports.npm_downloads_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["react"]})

    with patch(
        "max.imports.npm_downloads_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_metadata_fields() -> None:
    adapter = NpmDownloadsAdapter(config={"packages": ["react"]})

    with patch(
        "max.imports.npm_downloads_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_DOWNLOADS_RESPONSE)
        signals = await adapter.fetch(limit=10)

    meta = signals[0].metadata
    assert "package" in meta
    assert "total_downloads" in meta
    assert "daily_average" in meta
    assert "growth_rate_pct" in meta
    assert "moving_average_7d" in meta
    assert "start_date" in meta
    assert "end_date" in meta
    assert meta["start_date"] == "2026-04-01"
    assert meta["end_date"] == "2026-04-07"
