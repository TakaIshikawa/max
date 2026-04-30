"""Tests for the PyPI release history source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.pypi_releases import PyPIReleasesAdapter
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


def _pypi_payload() -> dict:
    return {
        "info": {
            "name": "FastAPI",
            "summary": "FastAPI framework",
            "description": "Release notes and project description.",
            "author": "Sebastian Ramirez",
            "classifiers": [
                "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
                "Topic :: Software Development :: Libraries :: Python Modules",
            ],
            "requires_python": ">=3.8",
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
            "0.111.0rc1": [
                {
                    "upload_time_iso_8601": "2026-04-15T08:00:00.000000Z",
                    "filename": "fastapi-0.111.0rc1-py3-none-any.whl",
                }
            ],
            "0.109.0": [
                {
                    "upload_time": "2026-03-25T09:00:00",
                    "filename": "fastapi-0.109.0.tar.gz",
                    "yanked": True,
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_fetches_recent_release_signals_from_configured_packages() -> None:
    adapter = PyPIReleasesAdapter(
        config={
            "packages": ["FastAPI"],
            "max_releases_per_package": 2,
            "base_url": "https://example.test/pypi",
        }
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        assert method == "GET"
        assert url == "https://example.test/pypi/fastapi/json"
        return _response(_pypi_payload())

    with patch("max.sources.pypi_releases.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["FastAPI@0.110.0", "FastAPI@0.109.0"]
    first = signals[0]
    assert first.source_adapter == "pypi_releases"
    assert first.source_type == SignalSourceType.ROADMAP
    assert first.url == "https://pypi.org/project/fastapi/0.110.0/"
    assert first.author == "Sebastian Ramirez"
    assert first.published_at is not None
    assert {"python", "pypi", "release", "fastapi", "devtools"} <= set(first.tags)
    assert first.metadata["signal_role"] == "adoption"
    assert first.metadata["package_name"] == "FastAPI"
    assert first.metadata["version"] == "0.110.0"
    assert first.metadata["release_url"] == "https://pypi.org/project/fastapi/0.110.0/"
    assert first.metadata["upload_time"] == "2026-04-10T12:30:00+00:00"
    assert first.metadata["classifiers"] == [
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ]
    assert first.metadata["project_urls"]["Source"] == "https://github.com/fastapi/fastapi"


@pytest.mark.asyncio
async def test_prereleases_are_included_when_configured() -> None:
    adapter = PyPIReleasesAdapter(
        config={
            "packages": ["fastapi"],
            "max_releases_per_package": 3,
            "include_prereleases": True,
        }
    )

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        return _response(_pypi_payload())

    with patch("max.sources.pypi_releases.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["version"] for signal in signals] == [
        "0.111.0rc1",
        "0.110.0",
        "0.109.0",
    ]
    assert signals[0].metadata["prerelease"] is True
    assert "prerelease" in signals[0].tags


@pytest.mark.asyncio
async def test_failed_package_is_skipped_without_failing_fetch() -> None:
    adapter = PyPIReleasesAdapter(config={"packages": ["missing", "fastapi"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/missing/json"):
            return _response({}, status_code=404)
        if url.endswith("/fastapi/json"):
            return _response(_pypi_payload())
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_releases.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert [signal.metadata["package_name"] for signal in signals] == ["FastAPI", "FastAPI"]


@pytest.mark.asyncio
async def test_malformed_releases_are_skipped() -> None:
    adapter = PyPIReleasesAdapter(config={"packages": ["broken", "empty"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url.endswith("/broken/json"):
            return _response({"info": {"name": "broken"}, "releases": []})
        if url.endswith("/empty/json"):
            return _response({"info": {"name": "empty"}, "releases": {"1.0.0": [{}]}})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pypi_releases.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert signals == []
