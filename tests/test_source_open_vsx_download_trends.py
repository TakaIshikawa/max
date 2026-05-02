"""Tests for Open VSX download trend source adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from max.sources.base import _circuit_breakers
from max.sources.open_vsx_download_trends import (
    OpenVsxDownloadTrendsAdapter,
    _extension_pairs,
    _stable_id,
)
from max.types.signal import SignalSourceType


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    _circuit_breakers.clear()
    yield
    _circuit_breakers.clear()


def _response(
    status_code: int,
    payload: dict | list | None = None,
    *,
    url: str = "https://open-vsx.org/api/redhat/vscode-yaml",
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload if payload is not None else {},
        request=httpx.Request("GET", url),
    )


def test_config_parsing_and_helpers() -> None:
    adapter = OpenVsxDownloadTrendsAdapter(
        config={
            "extensions": [
                " redhat/vscode-yaml ",
                "redhat.vscode-yaml",
                {"namespace": "openai", "name": "chatgpt"},
                {"namespace": "bad"},
                "",
                42,
            ],
            "open_vsx_api_url": " https://open-vsx.example/api/ ",
            "max_results": "7",
            "timeout": "12.5",
        }
    )

    assert adapter.extensions == [("redhat", "vscode-yaml"), ("openai", "chatgpt")]
    assert _extension_pairs("publisher.extension-name") == [("publisher", "extension-name")]
    assert adapter.open_vsx_api_url == "https://open-vsx.example/api"
    assert adapter.max_results == 7
    assert adapter.timeout == 12.5


@pytest.mark.asyncio
async def test_fetch_converts_extension_stats_to_deterministic_signal() -> None:
    adapter = OpenVsxDownloadTrendsAdapter(
        config={
            "extensions": ["redhat/vscode-yaml"],
            "open_vsx_api_url": "https://open-vsx.example/api",
            "timeout": 9,
        }
    )
    payload = {
        "namespace": "redhat",
        "name": "vscode-yaml",
        "displayName": "YAML",
        "version": "1.2.3",
        "downloadCount": 123456,
        "averageRating": 4.7,
        "reviewCount": 31,
    }

    with patch("max.sources.open_vsx_download_trends.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(return_value=_response(200, payload))
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    mock_cls.assert_called_once_with(timeout=9.0)
    mock_client.request.assert_awaited_once_with(
        "GET",
        "https://open-vsx.example/api/redhat/vscode-yaml",
        headers={"User-Agent": "max-open-vsx-download-trends-adapter/0.1"},
    )

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id == _stable_id("redhat/vscode-yaml", 123456, 4.7, 31)
    assert signal.source_type == SignalSourceType.MARKET
    assert signal.source_adapter == "open_vsx_download_trends"
    assert signal.title == "YAML Open VSX download trend"
    assert signal.content == (
        "redhat/vscode-yaml recorded 123,456 total Open VSX downloads "
        "with an average rating of 4.7 across 31 reviews."
    )
    assert signal.url == "https://open-vsx.org/extension/redhat/vscode-yaml"
    assert signal.author == "redhat"
    assert signal.published_at == signal.fetched_at
    assert "open-vsx" in signal.tags
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["extension_id"] == "redhat/vscode-yaml"
    assert signal.metadata["downloads"] == 123456
    assert signal.metadata["average_rating"] == 4.7
    assert signal.metadata["review_count"] == 31
    assert signal.metadata["api_url"] == "https://open-vsx.example/api/redhat/vscode-yaml"


@pytest.mark.asyncio
async def test_fetch_skips_http_failures_and_malformed_records() -> None:
    adapter = OpenVsxDownloadTrendsAdapter(
        config={"extensions": ["missing/extension", "bad/record", "ok/tool"]}
    )

    with patch("max.sources.open_vsx_download_trends.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(
            side_effect=[
                _response(404),
                _response(200, {"namespace": "bad", "name": "record"}),
                _response(200, {"namespace": "ok", "name": "tool", "downloadCount": 9}),
            ]
        )
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["extension_id"] == "ok/tool"
    assert signals[0].metadata["downloads"] == 9


@pytest.mark.asyncio
async def test_fetch_empty_config_returns_empty_without_http() -> None:
    adapter = OpenVsxDownloadTrendsAdapter(config={})

    with patch("max.sources.open_vsx_download_trends.httpx.AsyncClient") as mock_cls:
        assert await adapter.fetch(limit=10) == []

    mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_respects_limit_and_max_results() -> None:
    adapter = OpenVsxDownloadTrendsAdapter(
        config={
            "extensions": ["one/tool", "two/tool", "three/tool"],
            "max_results": 2,
        }
    )

    with patch("max.sources.open_vsx_download_trends.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.request = AsyncMock(
            side_effect=[
                _response(200, {"namespace": "one", "name": "tool", "downloadCount": 1}),
                _response(200, {"namespace": "two", "name": "tool", "downloadCount": 2}),
            ]
        )
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert [signal.metadata["extension_id"] for signal in signals] == ["one/tool", "two/tool"]
    assert mock_client.request.await_count == 2
