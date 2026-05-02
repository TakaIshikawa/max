"""Tests for the Hex.pm download trends source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.hexpm_download_trends import DEFAULT_PACKAGES, HexPmDownloadTrendsAdapter
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
    adapter = HexPmDownloadTrendsAdapter(
        config={"packages": ["Oban", "phoenix"], "period": "week"}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/oban"):
            return _response(
                {
                    "name": "oban",
                    "downloads": {
                        "all": 72_000_000,
                        "recent": 1_250_000,
                        "day": 42_000,
                        "week": 290_000,
                    },
                    "updated_at": "2026-04-20T12:30:00.000Z",
                }
            )
        if url.endswith("/phoenix"):
            return _response(
                {
                    "name": "phoenix",
                    "downloads": {
                        "all": 98_000_000,
                        "recent": 1_800_000,
                        "day": 71_000,
                        "week": 450_000,
                    },
                    "updated_at": "2026-04-22T08:00:00.000Z",
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hexpm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["package_name"] for signal in signals] == ["oban", "phoenix"]
    assert all(signal.source_adapter == "hexpm_download_trends" for signal in signals)
    assert all(signal.source_type == SignalSourceType.MARKET for signal in signals)

    first = signals[0]
    assert first.id == "hexpm_download_trends:oban:week"
    assert first.title == "oban Hex.pm download trend"
    assert first.content == "oban recorded 290,000 Hex.pm downloads for the last week."
    assert first.url == "https://hex.pm/packages/oban"
    assert first.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert first.metadata["signal_role"] == "market"
    assert first.metadata["package_ecosystem"] == "hexpm"
    assert first.metadata["hexpm_name"] == "oban"
    assert first.metadata["period"] == "week"
    assert first.metadata["time_window"] == "the last week"
    assert first.metadata["downloads"] == 290_000
    assert first.metadata["download_count"] == 290_000
    assert first.metadata["total_downloads"] == 72_000_000
    assert first.metadata["recent_downloads"] == 1_250_000
    assert first.metadata["daily_downloads"] == 42_000
    assert first.metadata["weekly_downloads"] == 290_000
    assert first.metadata["source_url"] == "https://hex.pm/packages/oban"
    assert first.metadata["api_url"] == "https://hex.pm/api/packages/oban"
    assert {"elixir", "erlang", "beam", "hexpm", "downloads", "downloads-week", "oban"} <= set(
        first.tags
    )


@pytest.mark.asyncio
async def test_defaults_and_custom_api_base_are_used() -> None:
    adapter = HexPmDownloadTrendsAdapter(
        config={"api_base_url": "https://hex.example/api/", "max_items": 1}
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        return _response({"name": DEFAULT_PACKAGES[0], "downloads": {"recent": "1200"}})

    with patch("max.sources.hexpm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert adapter.packages == DEFAULT_PACKAGES
    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == DEFAULT_PACKAGES[0]
    assert signals[0].metadata["downloads"] == 1_200
    assert urls == [f"https://hex.example/api/packages/{DEFAULT_PACKAGES[0]}"]


@pytest.mark.asyncio
async def test_malformed_responses_and_missing_period_downloads_are_skipped() -> None:
    adapter = HexPmDownloadTrendsAdapter(
        config={
            "packages": ["not-object", "missing-downloads", "bad-downloads", "valid"],
            "period": "recent",
        }
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/not-object"):
            return _response([{"name": "not-object", "downloads": {"recent": 10}}])
        if url.endswith("/missing-downloads"):
            return _response({"name": "missing-downloads", "downloads": {"week": 10}})
        if url.endswith("/bad-downloads"):
            return _response({"name": "bad-downloads", "downloads": {"recent": "nope"}})
        if url.endswith("/valid"):
            return _response({"name": "valid", "downloads": {"recent": 22_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hexpm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "valid"
    assert signals[0].metadata["downloads"] == 22_000


@pytest.mark.asyncio
async def test_api_error_does_not_fail_whole_fetch() -> None:
    adapter = HexPmDownloadTrendsAdapter(config={"packages": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/unavailable"):
            return _response({}, status_code=503)
        if url.endswith("/available"):
            return _response({"name": "available", "downloads": {"recent": 55_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hexpm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "available"


@pytest.mark.asyncio
async def test_min_downloads_limit_and_signal_ids_are_deterministic() -> None:
    adapter = HexPmDownloadTrendsAdapter(
        config={"packages": ["small", "popular", "ignored"], "min_downloads": 50_000}
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        if url.endswith("/small"):
            return _response({"name": "small", "downloads": {"recent": 49_999}})
        if url.endswith("/popular"):
            return _response({"name": "popular", "downloads": {"recent": 50_000}})
        if url.endswith("/ignored"):
            return _response({"name": "ignored", "downloads": {"recent": 99_000}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.hexpm_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        first = await adapter.fetch(limit=1)
        second = await adapter.fetch(limit=1)

    assert len(first) == 1
    assert first[0].metadata["package_name"] == "popular"
    assert [signal.id for signal in first] == [signal.id for signal in second]
    assert urls == [
        "https://hex.pm/api/packages/small",
        "https://hex.pm/api/packages/popular",
        "https://hex.pm/api/packages/small",
        "https://hex.pm/api/packages/popular",
    ]
