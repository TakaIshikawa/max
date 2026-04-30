"""Tests for the Pub.dev source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from max.sources.base import _circuit_breakers
from max.sources.pubdev import PubDevAdapter
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
async def test_fetch_configured_packages_as_registry_signals() -> None:
    adapter = PubDevAdapter(config={"packages": ["Riverpod"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url == "https://pub.dev/api/packages/riverpod":
            return _response(
                {
                    "name": "riverpod",
                    "latest": {
                        "version": "3.0.3",
                        "published": "2026-04-20T12:30:00.000000Z",
                        "pubspec": {
                            "description": "A reactive caching and data-binding framework.",
                            "homepage": "https://riverpod.dev",
                            "repository": "https://github.com/rrousselGit/riverpod",
                            "documentation": "https://riverpod.dev/docs",
                            "topics": ["state-management", "provider"],
                        },
                    },
                    "publisher": "dash-overflow.net",
                }
            )
        if url == "https://pub.dev/api/packages/riverpod/score":
            return _response(
                {
                    "grantedPoints": 150,
                    "maxPoints": 160,
                    "likeCount": 7200,
                    "popularityScore": 0.98,
                    "tags": ["platform:android", "platform:ios", "sdk:flutter"],
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pubdev.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "pubdev:riverpod:3.0.3"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "pubdev"
    assert signal.title == "riverpod@3.0.3"
    assert signal.url == "https://pub.dev/packages/riverpod"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.metadata["package_ecosystem"] == "pubdev"
    assert signal.metadata["package_name"] == "riverpod"
    assert signal.metadata["latest_version"] == "3.0.3"
    assert signal.metadata["popularity_score"] == 0.98
    assert signal.metadata["likes"] == 7200
    assert signal.metadata["pub_points"] == 150
    assert signal.metadata["max_points"] == 160
    assert signal.metadata["repository_url"] == "https://github.com/rrousselGit/riverpod"
    assert signal.metadata["homepage"] == "https://riverpod.dev"
    assert signal.metadata["documentation"] == "https://riverpod.dev/docs"
    assert signal.metadata["publisher"] == "dash-overflow.net"
    assert signal.metadata["api_url"] == "https://pub.dev/api/packages/riverpod"
    assert signal.metadata["score_api_url"] == "https://pub.dev/api/packages/riverpod/score"
    assert signal.metadata["source_url"] == "https://pub.dev/packages/riverpod"
    assert {"dart", "flutter", "pubdev", "state-management", "android", "ios"} <= set(
        signal.tags
    )
    assert signal.credibility > 0.9


@pytest.mark.asyncio
async def test_missing_optional_metrics_still_emits_signal() -> None:
    adapter = PubDevAdapter(config={"packages": ["minimal"], "base_url": "https://example.test"})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url == "https://example.test/api/packages/minimal":
            return _response(
                {
                    "name": "minimal",
                    "latest": {
                        "version": "1.2.0",
                        "pubspec": {"description": "Small Dart utility."},
                    },
                }
            )
        if url == "https://example.test/api/packages/minimal/score":
            return _response({"tags": ["sdk:dart"]})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pubdev.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == "pubdev:minimal:1.2.0"
    assert signal.title == "minimal@1.2.0"
    assert signal.url == "https://example.test/packages/minimal"
    assert signal.published_at is None
    assert signal.metadata["popularity"] is None
    assert signal.metadata["likes"] is None
    assert signal.metadata["pub_points"] is None
    assert signal.metadata["repository_url"] is None
    assert signal.metadata["homepage"] is None
    assert signal.credibility == 0.1


@pytest.mark.asyncio
async def test_score_request_failure_keeps_metadata_signal() -> None:
    adapter = PubDevAdapter(config={"packages": ["provider"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url == "https://pub.dev/api/packages/provider":
            return _response(
                {
                    "name": "provider",
                    "latest": {
                        "version": "6.1.5",
                        "published": "2026-04-18T09:00:00Z",
                        "pubspec": {"description": "InheritedWidget wrapper."},
                    },
                }
            )
        if url == "https://pub.dev/api/packages/provider/score":
            return _response({}, status_code=503)
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pubdev.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "provider"
    assert signals[0].metadata["likes"] is None


@pytest.mark.asyncio
async def test_metadata_request_failure_skips_package() -> None:
    adapter = PubDevAdapter(config={"packages": ["unavailable", "available"]})

    async def request(method: str, url: str, **kwargs) -> MagicMock:
        if url == "https://pub.dev/api/packages/unavailable":
            return _response({}, status_code=503)
        if url == "https://pub.dev/api/packages/available":
            return _response(
                {
                    "name": "available",
                    "latest": {
                        "version": "1.0.0",
                        "pubspec": {"description": "Available package."},
                    },
                }
            )
        if url == "https://pub.dev/api/packages/available/score":
            return _response({"likeCount": 12, "grantedPoints": 120})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.pubdev.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(request)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_name"] == "available"
    assert signals[0].metadata["likes"] == 12
