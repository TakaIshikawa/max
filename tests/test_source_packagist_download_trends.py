"""Tests for the Packagist download trends source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.packagist_download_trends import PackagistDownloadTrendsAdapter
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
async def test_fetch_configured_packages_as_market_signals() -> None:
    adapter = PackagistDownloadTrendsAdapter(
        config={"packages": ["Laravel/Framework", "symfony/console"]}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/packages/laravel/framework.json"):
            return _response(
                {
                    "package": {
                        "name": "laravel/framework",
                        "url": "https://packagist.org/packages/laravel/framework",
                        "repository": "https://github.com/laravel/framework",
                        "time": "2026-04-20T12:30:00+00:00",
                        "downloads": {
                            "total": 420_000_000,
                            "monthly": 9_500_000,
                            "daily": 320_000,
                        },
                    }
                }
            )
        if url.endswith("/packages/symfony/console.json"):
            return _response(
                {
                    "package": {
                        "name": "symfony/console",
                        "repository": "https://github.com/symfony/console",
                        "downloads": {
                            "total": 330_000_000,
                            "monthly": 8_100_000,
                            "daily": 270_000,
                        },
                    }
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.packagist_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["package_name"] for signal in signals] == [
        "laravel/framework",
        "symfony/console",
    ]
    assert all(signal.source_adapter == "packagist_download_trends" for signal in signals)
    assert all(signal.source_type == SignalSourceType.MARKET for signal in signals)

    first = signals[0]
    assert first.id == "packagist_download_trends:laravel/framework"
    assert first.title == "laravel/framework Packagist download trend"
    assert first.url == "https://packagist.org/packages/laravel/framework"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.metadata["package_ecosystem"] == "packagist"
    assert first.metadata["downloads"] == 420_000_000
    assert first.metadata["downloads_total"] == 420_000_000
    assert first.metadata["downloads_monthly"] == 9_500_000
    assert first.metadata["downloads_daily"] == 320_000
    assert first.metadata["repository"] == "https://github.com/laravel/framework"
    assert first.metadata["api_url"] == "https://packagist.org/packages/laravel/framework.json"
    assert first.metadata["signal_role"] == "market"
    assert first.metadata["trend_points"] == [
        {"window": "total", "downloads": 420_000_000},
        {"window": "monthly", "downloads": 9_500_000},
        {"window": "daily", "downloads": 320_000},
    ]
    assert {"php", "packagist", "package", "downloads", "laravel", "framework"} <= set(first.tags)


@pytest.mark.asyncio
async def test_max_results_base_url_and_deduped_normalized_packages_are_used() -> None:
    adapter = PackagistDownloadTrendsAdapter(
        config={
            "packages": [" Vendor/Package ", "vendor/package", "ignored/package"],
            "max_results": 1,
            "base_url": "https://example.test",
        }
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        if url == "https://example.test/packages/vendor/package.json":
            return _response(
                {
                    "package": {
                        "name": "vendor/package",
                        "downloads": {"total": 12_000, "monthly": 1_000, "daily": 40},
                    }
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.packagist_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "vendor/package"
    assert signals[0].url == "https://example.test/packages/vendor/package"
    assert urls == ["https://example.test/packages/vendor/package.json"]


@pytest.mark.asyncio
async def test_missing_stats_and_malformed_payloads_are_skipped() -> None:
    adapter = PackagistDownloadTrendsAdapter(
        config={"packages": ["not-object", "missing-package", "missing-stats", "valid"]}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/packages/not-object.json"):
            return _response([{"package": {"name": "not-object"}}])
        if url.endswith("/packages/missing-package.json"):
            return _response({"meta": {"status": "ok"}})
        if url.endswith("/packages/missing-stats.json"):
            return _response({"package": {"name": "missing-stats"}})
        if url.endswith("/packages/valid.json"):
            return _response({"package": {"name": "valid", "downloads": {"total": 22_000}}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.packagist_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "valid"
    assert signals[0].metadata["downloads_total"] == 22_000
    assert signals[0].metadata["downloads_monthly"] is None
    assert signals[0].metadata["downloads_daily"] is None


@pytest.mark.asyncio
async def test_http_failure_does_not_fail_whole_fetch() -> None:
    adapter = PackagistDownloadTrendsAdapter(config={"packages": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/packages/unavailable.json"):
            return _response({}, status_code=503)
        if url.endswith("/packages/available.json"):
            return _response({"package": {"name": "available", "downloads": {"total": 55_000}}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.packagist_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "available"
