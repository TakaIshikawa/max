"""Tests for the PyPI maintainer activity source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.pypi_maintainer_activity import PyPIMaintainerActivityAdapter
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


def _pypi_payload() -> dict:
    return {
        "info": {
            "name": "FastAPI",
            "version": "0.110.0",
            "summary": "FastAPI framework",
            "author": "Sebastian Ramirez",
            "author_email": "sebastian@example.com",
            "maintainer": "FastAPI maintainers",
            "maintainer_email": "team@example.com",
            "classifiers": [
                "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
                "Topic :: Software Development :: Libraries :: Python Modules",
            ],
            "requires_python": ">=3.8",
            "license": "MIT",
            "package_url": "https://pypi.org/project/fastapi/",
            "project_urls": {
                "Homepage": "https://fastapi.tiangolo.com/",
                "Source": "https://github.com/fastapi/fastapi",
            },
        },
        "releases": {
            "0.110.0": [
                {
                    "upload_time_iso_8601": "2026-04-10T12:30:00.000000Z",
                    "filename": "fastapi-0.110.0-py3-none-any.whl",
                }
            ],
            "0.109.0": [
                {
                    "upload_time": "2026-03-25T09:00:00",
                    "filename": "fastapi-0.109.0.tar.gz",
                    "yanked": True,
                }
            ],
            "0.108.0": [
                {
                    "upload_time_iso_8601": "2026-02-01T10:00:00.000000Z",
                    "filename": "fastapi-0.108.0.tar.gz",
                }
            ],
        },
    }


def test_adapter_properties_and_custom_config() -> None:
    adapter = PyPIMaintainerActivityAdapter(
        config={
            "packages": ["FastAPI", "fastapi", "httpx"],
            "watchlist_terms": ["pydantic"],
            "pypi_api_url": "https://example.test/pypi/",
            "max_releases": "2",
            "timeout": "12.5",
        }
    )

    assert adapter.name == "pypi_maintainer_activity"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.packages == ["fastapi", "httpx", "pydantic"]
    assert adapter.pypi_api_url == "https://example.test/pypi"
    assert adapter.max_releases == 2
    assert adapter.timeout == 12.5


@pytest.mark.asyncio
async def test_fetches_one_maintainer_activity_signal_per_configured_package() -> None:
    adapter = PyPIMaintainerActivityAdapter(
        config={
            "packages": ["FastAPI"],
            "pypi_api_url": "https://example.test/pypi",
            "max_releases": 2,
        }
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        assert url == "https://example.test/pypi/fastapi/json"
        assert kwargs["headers"]["User-Agent"] == "max-pypi-maintainer-activity-adapter/0.1"
        return _response(_pypi_payload())

    with patch("max.sources.pypi_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "pypi-maintainer-activity:fastapi"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "pypi_maintainer_activity"
    assert signal.title == "FastAPI PyPI maintainer activity"
    assert "2 PyPI maintainers" in signal.content
    assert "last released 2026-04-10" in signal.content
    assert signal.url == "https://pypi.org/project/fastapi/"
    assert signal.author == "FastAPI maintainers"
    assert signal.published_at is not None
    assert {"python", "pypi", "registry", "maintainer-activity", "package-health", "devtools"} <= set(signal.tags)
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["signal_kind"] == "maintainer_activity"
    assert signal.metadata["package_ecosystem"] == "pypi"
    assert signal.metadata["package_name"] == "FastAPI"
    assert signal.metadata["pypi_name"] == "FastAPI"
    assert signal.metadata["requested_package"] == "fastapi"
    assert signal.metadata["latest_version"] == "0.110.0"
    assert signal.metadata["maintainer_count"] == 2
    assert signal.metadata["maintainers"] == [
        {"role": "maintainer", "name": "FastAPI maintainers", "email": "team@example.com"},
        {"role": "author", "name": "Sebastian Ramirez", "email": "sebastian@example.com"},
    ]
    assert signal.metadata["project_urls"]["Source"] == "https://github.com/fastapi/fastapi"
    assert signal.metadata["api_url"] == "https://example.test/pypi/fastapi/json"
    assert signal.metadata["release_health"]["latest_release_at"] == "2026-04-10T12:30:00+00:00"
    assert signal.metadata["release_health"]["oldest_release_at"] == "2026-03-25T09:00:00+00:00"
    assert signal.metadata["release_health"]["total_releases_analyzed"] == 2
    assert signal.metadata["release_health"]["average_days_between_releases"] == 16.1
    assert [row["version"] for row in signal.metadata["release_health"]["recent_releases"]] == [
        "0.110.0",
        "0.109.0",
    ]


@pytest.mark.asyncio
async def test_missing_maintainers_and_release_data_degrade_gracefully() -> None:
    adapter = PyPIMaintainerActivityAdapter(config={"packages": ["empty"]})
    payload = {
        "info": {
            "name": "empty",
            "version": "1.0.0",
            "summary": "Sparse metadata",
            "package_url": "https://pypi.org/project/empty/",
        },
        "releases": {"1.0.0": [{}]},
    }

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(payload)

    with patch("max.sources.pypi_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.author is None
    assert signal.published_at is None
    assert "0 PyPI maintainers" in signal.content
    assert "no dated releases" in signal.content
    assert signal.metadata["maintainers"] == []
    assert signal.metadata["release_health"]["latest_release_at"] is None
    assert signal.metadata["health_indicators"]["has_maintainers"] is False
    assert signal.metadata["health_indicators"]["has_release_data"] is False


@pytest.mark.asyncio
async def test_malformed_or_failed_package_responses_are_skipped() -> None:
    adapter = PyPIMaintainerActivityAdapter(config={"packages": ["missing", "broken", "fastapi"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/missing/json"):
            return _response({}, status_code=404)
        if url.endswith("/broken/json"):
            return _response(["not", "a", "dict"])
        if url.endswith("/fastapi/json"):
            return _response(_pypi_payload())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_maintainer_activity.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["package_name"] for signal in signals] == ["FastAPI"]
