"""Tests for the PyPI download trends source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.pypi_download_trends import PyPIDownloadTrendsAdapter
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers() -> None:
    _circuit_breakers.clear()


def _response(payload: dict, *, status_code: int = 200) -> MagicMock:
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
async def test_fetch_configured_packages_as_market_signals() -> None:
    adapter = PyPIDownloadTrendsAdapter(
        config={"packages": ["FastAPI", "httpx"], "period": "week"}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/fastapi/recent"):
            return _response({"data": {"last_day": 12_000, "last_week": 90_000, "last_month": 320_000}})
        if url.endswith("/httpx/recent"):
            return _response({"data": {"last_day": 8_000, "last_week": 75_000, "last_month": 280_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["package_name"] for signal in signals] == ["fastapi", "httpx"]
    assert all(signal.source_adapter == "pypi_download_trends" for signal in signals)
    assert all(signal.source_type == SignalSourceType.MARKET for signal in signals)

    first = signals[0]
    assert first.url == "https://pypi.org/project/fastapi/"
    assert first.metadata["recent_downloads"] == 90_000
    assert first.metadata["last_week"] == 90_000
    assert first.metadata["package_url"] == "https://pypi.org/project/fastapi/"
    assert first.metadata["pypistats_url"] == "https://pypistats.org/api/packages/fastapi/recent"
    assert first.metadata["signal_role"] == "market"
    assert {"python", "pypi", "package", "downloads-week", "fastapi"} <= set(first.tags)


@pytest.mark.asyncio
async def test_min_downloads_filters_weak_adoption_signals() -> None:
    adapter = PyPIDownloadTrendsAdapter(
        config={"packages": ["small-lib", "popular-lib"], "min_downloads": 50_000}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/small-lib/recent"):
            return _response({"data": {"last_week": 49_999}})
        if url.endswith("/popular-lib/recent"):
            return _response({"data": {"last_week": 50_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "popular-lib"
    assert signals[0].metadata["recent_downloads"] == 50_000


@pytest.mark.asyncio
async def test_malformed_or_missing_download_fields_are_skipped() -> None:
    adapter = PyPIDownloadTrendsAdapter(
        config={"packages": ["missing", "malformed", "valid"], "period": "month"}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/missing/recent"):
            return _response({"data": {"last_week": 12_000}})
        if url.endswith("/malformed/recent"):
            return _response({"data": {"last_month": "not-a-number"}})
        if url.endswith("/valid/recent"):
            return _response({"data": {"last_day": 900, "last_week": 5_000, "last_month": 22_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "valid"
    assert signals[0].metadata["period"] == "month"
    assert signals[0].metadata["period_field"] == "last_month"
    assert signals[0].metadata["recent_downloads"] == 22_000


@pytest.mark.asyncio
async def test_malformed_data_container_is_skipped_without_failing_fetch() -> None:
    adapter = PyPIDownloadTrendsAdapter(config={"packages": ["broken", "valid"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/broken/recent"):
            return _response({"data": [{"last_week": 10_000}]})
        if url.endswith("/valid/recent"):
            return _response({"data": {"last_week": 20_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "valid"


@pytest.mark.asyncio
async def test_retryable_failure_retries_and_continues() -> None:
    adapter = PyPIDownloadTrendsAdapter(config={"packages": ["flaky", "steady"]})
    flaky_calls = 0

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        nonlocal flaky_calls
        if url.endswith("/flaky/recent"):
            flaky_calls += 1
            if flaky_calls == 1:
                return _response({}, status_code=503)
            return _response({"data": {"last_week": 30_000}})
        if url.endswith("/steady/recent"):
            return _response({"data": {"last_week": 40_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert flaky_calls == 2
    assert [signal.metadata["package_name"] for signal in signals] == ["flaky", "steady"]


@pytest.mark.asyncio
async def test_failed_package_does_not_fail_whole_fetch() -> None:
    adapter = PyPIDownloadTrendsAdapter(config={"packages": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/unavailable/recent"):
            return _response({}, status_code=503)
        if url.endswith("/available/recent"):
            return _response({"data": {"last_week": 55_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "available"
