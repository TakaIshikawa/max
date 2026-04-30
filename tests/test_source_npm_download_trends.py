"""Tests for the npm download trends source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.npm_download_trends import NpmDownloadTrendsAdapter
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
    adapter = NpmDownloadTrendsAdapter(
        config={"packages": ["React", "@modelcontextprotocol/sdk"], "period": "last-week"}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/last-week/react"):
            return _response(
                {
                    "downloads": 28_000_000,
                    "start": "2026-04-20",
                    "end": "2026-04-26",
                    "package": "react",
                }
            )
        if url.endswith("/last-week/@modelcontextprotocol/sdk"):
            return _response(
                {
                    "downloads": 125_000,
                    "start": "2026-04-20",
                    "end": "2026-04-26",
                    "package": "@modelcontextprotocol/sdk",
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.npm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["package_name"] for signal in signals] == [
        "react",
        "@modelcontextprotocol/sdk",
    ]
    assert all(signal.source_adapter == "npm_download_trends" for signal in signals)
    assert all(signal.source_type == SignalSourceType.MARKET for signal in signals)

    first = signals[0]
    assert first.url == "https://www.npmjs.com/package/react"
    assert first.metadata["downloads"] == 28_000_000
    assert first.metadata["period"] == "last-week"
    assert first.metadata["start"] == "2026-04-20"
    assert first.metadata["end"] == "2026-04-26"
    assert first.metadata["api_url"] == "https://api.npmjs.org/downloads/point/last-week/react"
    assert first.metadata["signal_role"] == "market"
    assert {"javascript", "npm", "package", "downloads-last-week", "react"} <= set(first.tags)


@pytest.mark.asyncio
async def test_empty_package_list_returns_no_signals_without_http_calls() -> None:
    adapter = NpmDownloadTrendsAdapter(config={"packages": []})

    with patch("max.sources.npm_download_trends.httpx.AsyncClient") as mock_cls:
        signals = await adapter.fetch(limit=10)

    assert signals == []
    mock_cls.assert_called_once()
    mock_cls.return_value.__aenter__.assert_awaited_once()
    mock_cls.return_value.request.assert_not_called()


@pytest.mark.asyncio
async def test_malformed_rows_are_skipped_without_failing_fetch() -> None:
    adapter = NpmDownloadTrendsAdapter(
        config={"packages": ["missing-downloads", "bad-downloads", "not-object", "valid"]}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/last-week/missing-downloads"):
            return _response({"package": "missing-downloads"})
        if url.endswith("/last-week/bad-downloads"):
            return _response({"downloads": "not-a-number", "package": "bad-downloads"})
        if url.endswith("/last-week/not-object"):
            return _response([{"downloads": 10_000, "package": "not-object"}])
        if url.endswith("/last-week/valid"):
            return _response({"downloads": 22_000, "package": "valid"})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.npm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "valid"
    assert signals[0].metadata["downloads"] == 22_000


@pytest.mark.asyncio
async def test_configured_period_alias_and_max_results_are_used() -> None:
    adapter = NpmDownloadTrendsAdapter(
        config={"packages": ["react", "vite"], "period": "month", "max_results": 1}
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        if url.endswith("/last-month/react"):
            return _response({"downloads": 120_000_000, "package": "react"})
        if url.endswith("/last-month/vite"):
            return _response({"downloads": 30_000_000, "package": "vite"})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.npm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert adapter.period == "last-month"
    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "react"
    assert urls == ["https://api.npmjs.org/downloads/point/last-month/react"]


@pytest.mark.asyncio
async def test_http_failure_does_not_fail_whole_fetch() -> None:
    adapter = NpmDownloadTrendsAdapter(config={"packages": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/last-week/unavailable"):
            return _response({}, status_code=503)
        if url.endswith("/last-week/available"):
            return _response({"downloads": 55_000, "package": "available"})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.npm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "available"
