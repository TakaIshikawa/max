"""Tests for the Packagist maintainer activity source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import _circuit_breakers
from max.sources.packagist_maintainer_activity import PackagistMaintainerActivityAdapter
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


def _laravel_payload() -> dict:
    return {
        "package": {
            "name": "laravel/framework",
            "description": "The Laravel Framework.",
            "url": "https://packagist.org/packages/laravel/framework",
            "repository": "https://github.com/laravel/framework",
            "downloads": {
                "total": 420_000_000,
                "monthly": 9_500_000,
                "daily": 320_000,
            },
            "maintainers": [
                {"name": "taylorotwell", "avatar": "https://example.test/taylor.png"},
                {"name": "driesvints"},
            ],
            "versions": {
                "v11.0.0": {
                    "version": "v11.0.0",
                    "version_normalized": "11.0.0.0",
                    "time": "2026-04-20T12:30:00+00:00",
                    "type": "library",
                    "license": ["MIT"],
                    "keywords": ["framework", "laravel"],
                    "authors": [
                        {
                            "name": "Taylor Otwell",
                            "email": "taylor@example.test",
                            "homepage": "https://laravel.com",
                        }
                    ],
                    "source": {"url": "https://github.com/laravel/framework"},
                },
                "v10.0.0": {
                    "version": "v10.0.0",
                    "version_normalized": "10.0.0.0",
                    "time": "2026-03-01T08:00:00+00:00",
                    "license": ["MIT"],
                },
                "dev-main": {
                    "version": "dev-main",
                    "time": "2026-05-01T00:00:00+00:00",
                },
            },
        }
    }


def test_adapter_properties_and_custom_config() -> None:
    adapter = PackagistMaintainerActivityAdapter(
        config={
            "packages": ["Laravel/Framework", "laravel/framework"],
            "package_names": ["symfony/console"],
            "watchlist_terms": ["composer/composer"],
            "base_url": "https://example.test/",
            "max_results": "7",
            "timeout": "12.5",
        }
    )

    assert adapter.name == "packagist_maintainer_activity"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.packages == ["laravel/framework", "composer/composer", "symfony/console"]
    assert adapter.base_url == "https://example.test"
    assert adapter.max_items == 7
    assert adapter.timeout == 12.5


@pytest.mark.asyncio
async def test_fetches_package_maintainer_activity_signal_with_metadata() -> None:
    adapter = PackagistMaintainerActivityAdapter(
        config={"packages": ["Laravel/Framework"], "base_url": "https://example.test"}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        assert url == "https://example.test/packages/laravel/framework.json"
        assert kwargs["headers"]["User-Agent"] == "max-packagist-maintainer-activity-adapter/0.1"
        return _response(_laravel_payload())

    with patch("max.sources.packagist_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "packagist-maintainer-activity:laravel/framework"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "packagist_maintainer_activity"
    assert signal.title == "laravel/framework Packagist maintainer activity"
    assert "2 Packagist maintainers" in signal.content
    assert "latest version v11.0.0" in signal.content
    assert "Total downloads: 420,000,000" in signal.content
    assert signal.url == "https://packagist.org/packages/laravel/framework"
    assert signal.author == "taylorotwell"
    assert signal.published_at is not None
    assert {"php", "packagist", "registry", "maintainer-activity", "package-health"} <= set(signal.tags)
    assert {"laravel", "framework", "mit"} <= set(signal.tags)
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["signal_kind"] == "maintainer_activity"
    assert signal.metadata["evidence_type"] == "package_health"
    assert signal.metadata["package_ecosystem"] == "packagist"
    assert signal.metadata["package_name"] == "laravel/framework"
    assert signal.metadata["packagist_name"] == "laravel/framework"
    assert signal.metadata["requested_package"] == "laravel/framework"
    assert signal.metadata["version"] == "v11.0.0"
    assert signal.metadata["latest_version"] == "v11.0.0"
    assert signal.metadata["maintainers"] == [
        {"role": "maintainer", "name": "taylorotwell", "avatar": "https://example.test/taylor.png"},
        {"role": "maintainer", "name": "driesvints"},
    ]
    assert signal.metadata["authors"] == [
        {
            "role": "author",
            "name": "Taylor Otwell",
            "email": "taylor@example.test",
            "homepage": "https://laravel.com",
        }
    ]
    assert signal.metadata["maintainer_count"] == 2
    assert signal.metadata["downloads"] == 420_000_000
    assert signal.metadata["monthly_downloads"] == 9_500_000
    assert signal.metadata["daily_downloads"] == 320_000
    assert signal.metadata["licenses"] == ["MIT"]
    assert signal.metadata["latest_release_at"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["release_health"]["latest_release_at"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["release_health"]["oldest_release_at"] == "2026-03-01T08:00:00+00:00"
    assert signal.metadata["release_health"]["total_releases_analyzed"] == 2
    assert signal.metadata["release_health"]["average_days_between_releases"] == 50.2
    assert signal.metadata["repository_url"] == "https://github.com/laravel/framework"
    assert signal.metadata["api_url"] == "https://example.test/packages/laravel/framework.json"


@pytest.mark.asyncio
async def test_sparse_package_response_degrades_without_crashing() -> None:
    adapter = PackagistMaintainerActivityAdapter(config={"packages": ["vendor/sparse"]})
    payload = {
        "package": {
            "name": "vendor/sparse",
            "description": "Sparse package metadata.",
            "versions": [
                {
                    "version": "1.0.0",
                    "time": "2026-01-05T00:00:00Z",
                }
            ],
        }
    }

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(payload)

    with patch("max.sources.packagist_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.author is None
    assert "0 Packagist maintainers" in signal.content
    assert signal.metadata["maintainers"] == []
    assert signal.metadata["downloads"] is None
    assert signal.metadata["health_indicators"]["has_maintainers"] is False
    assert signal.metadata["health_indicators"]["has_repository"] is False
    assert signal.metadata["latest_release_at"] == "2026-01-05T00:00:00+00:00"


@pytest.mark.asyncio
async def test_network_failures_and_malformed_payloads_are_skipped() -> None:
    adapter = PackagistMaintainerActivityAdapter(
        config={"packages": ["broken", "missing-package", "empty", "laravel/framework"]}
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/packages/broken.json"):
            raise httpx.RequestError("network down")
        if url.endswith("/packages/missing-package.json"):
            return _response({"meta": {"status": "ok"}})
        if url.endswith("/packages/empty.json"):
            return _response({"package": {"name": "empty"}})
        if url.endswith("/packages/laravel/framework.json"):
            return _response(_laravel_payload())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.packagist_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "laravel/framework"


@pytest.mark.asyncio
async def test_empty_fetch_behavior() -> None:
    adapter = PackagistMaintainerActivityAdapter(config={"packages": ["laravel/framework"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response([])

    with patch("max.sources.packagist_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        assert await adapter.fetch(limit=10) == []
        assert await adapter.fetch(limit=0) == []
