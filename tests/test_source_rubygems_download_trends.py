"""Tests for the RubyGems download trends source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.rubygems_download_trends import RubyGemsDownloadTrendsAdapter
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
async def test_fetch_configured_gems_as_market_signals() -> None:
    adapter = RubyGemsDownloadTrendsAdapter(config={"packages": ["Rails", "sidekiq"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/rails.json"):
            return _response(
                {
                    "name": "rails",
                    "version": "8.0.2",
                    "downloads": 620_000_000,
                    "version_downloads": 2_500_000,
                    "project_uri": "https://rubygems.org/gems/rails",
                    "version_created_at": "2026-04-15T10:00:00.000Z",
                }
            )
        if url.endswith("/sidekiq.json"):
            return _response(
                {
                    "name": "sidekiq",
                    "version": "7.3.9",
                    "downloads": 410_000_000,
                    "version_downloads": 850_000,
                    "project_uri": "https://rubygems.org/gems/sidekiq",
                    "version_created_at": "2026-03-20T08:30:00.000Z",
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["gem_name"] for signal in signals] == ["rails", "sidekiq"]
    assert all(signal.source_adapter == "rubygems_download_trends" for signal in signals)
    assert all(signal.source_type == SignalSourceType.MARKET for signal in signals)

    first = signals[0]
    assert first.id == "rubygems_download_trends:rails:8.0.2"
    assert first.title == "rails RubyGems download trend"
    assert first.content == "rails recorded 620,000,000 total RubyGems downloads for version 8.0.2."
    assert first.url == "https://rubygems.org/gems/rails"
    assert first.published_at == datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
    assert first.metadata["package_ecosystem"] == "rubygems"
    assert first.metadata["package_name"] == "rails"
    assert first.metadata["downloads"] == 620_000_000
    assert first.metadata["download_count"] == 620_000_000
    assert first.metadata["version"] == "8.0.2"
    assert first.metadata["version_downloads"] == 2_500_000
    assert first.metadata["version_created_at"] == "2026-04-15T10:00:00+00:00"
    assert first.metadata["source_url"] == "https://rubygems.org/gems/rails"
    assert first.metadata["api_url"] == "https://rubygems.org/api/v1/gems/rails.json"
    assert first.metadata["signal_role"] == "market"
    assert {"ruby", "rubygems", "package", "downloads", "rails"} <= set(first.tags)


@pytest.mark.asyncio
async def test_missing_optional_fields_use_stable_defaults() -> None:
    adapter = RubyGemsDownloadTrendsAdapter(config={"packages": ["minimal"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/minimal.json"):
            return _response({"downloads": "1200"})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "rubygems_download_trends:minimal:unknown"
    assert signal.url == "https://rubygems.org/gems/minimal"
    assert signal.published_at is None
    assert signal.metadata["gem_name"] == "minimal"
    assert signal.metadata["downloads"] == 1_200
    assert signal.metadata["version"] == ""
    assert signal.metadata["version_downloads"] is None
    assert signal.metadata["source_url"] == "https://rubygems.org/gems/minimal"


@pytest.mark.asyncio
async def test_malformed_responses_and_missing_downloads_are_skipped() -> None:
    adapter = RubyGemsDownloadTrendsAdapter(
        config={"packages": ["not-object", "missing-downloads", "bad-downloads", "valid"]}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/not-object.json"):
            return _response([{"name": "not-object", "downloads": 10}])
        if url.endswith("/missing-downloads.json"):
            return _response({"name": "missing-downloads", "version": "1.0.0"})
        if url.endswith("/bad-downloads.json"):
            return _response({"name": "bad-downloads", "downloads": "not-a-number"})
        if url.endswith("/valid.json"):
            return _response({"name": "valid", "version": "2.0.0", "downloads": 22_000})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["gem_name"] == "valid"
    assert signals[0].metadata["downloads"] == 22_000


@pytest.mark.asyncio
async def test_api_error_does_not_fail_whole_fetch() -> None:
    adapter = RubyGemsDownloadTrendsAdapter(config={"packages": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/unavailable.json"):
            return _response({}, status_code=503)
        if url.endswith("/available.json"):
            return _response({"name": "available", "version": "1.1.0", "downloads": 55_000})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["gem_name"] == "available"


@pytest.mark.asyncio
async def test_min_downloads_and_max_items_are_used() -> None:
    adapter = RubyGemsDownloadTrendsAdapter(
        config={"packages": ["small", "popular", "ignored"], "min_downloads": 50_000, "max_items": 1}
    )
    urls: list[str] = []

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        urls.append(url)
        if url.endswith("/small.json"):
            return _response({"name": "small", "version": "0.1.0", "downloads": 49_999})
        if url.endswith("/popular.json"):
            return _response({"name": "popular", "version": "1.0.0", "downloads": 50_000})
        if url.endswith("/ignored.json"):
            return _response({"name": "ignored", "version": "1.0.0", "downloads": 99_000})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.rubygems_download_trends.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["gem_name"] == "popular"
    assert urls == [
        "https://rubygems.org/api/v1/gems/small.json",
        "https://rubygems.org/api/v1/gems/popular.json",
    ]
