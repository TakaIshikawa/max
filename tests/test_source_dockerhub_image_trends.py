"""Tests for the Docker Hub image trends source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.dockerhub_image_trends import (
    DockerHubImageTrendsAdapter,
    parse_repository_signal,
)
from max.types.signal import SignalSourceType


MOCK_REPOSITORY = {
    "namespace": "library",
    "name": "nginx",
    "repository_type": "image",
    "description": "Official build of Nginx.",
    "is_automated": False,
    "is_official": True,
    "star_count": 20_000,
    "pull_count": 1_500_000_000,
    "last_updated": "2026-04-20T12:30:00Z",
}


def _response(payload: object, *, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "https://hub.docker.test/v2/namespaces/library/repositories/nginx")
    return httpx.Response(status_code, json=payload, request=request)


def test_parse_repository_signal_preserves_trend_metadata() -> None:
    signal = parse_repository_signal(MOCK_REPOSITORY, repo_id=("library", "nginx"))

    assert signal.id == "dockerhub_image_trends:library/nginx"
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "dockerhub_image_trends"
    assert signal.title == "library/nginx Docker Hub image trend"
    assert signal.url == "https://hub.docker.com/_/nginx"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert "1,500,000,000 pulls" in signal.content
    assert "20,000 stars" in signal.content
    assert signal.metadata["signal_role"] == "market"
    assert signal.metadata["repository_name"] == "library/nginx"
    assert signal.metadata["pull_count"] == 1_500_000_000
    assert signal.metadata["star_count"] == 20_000
    assert signal.metadata["last_updated"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["description"] == "Official build of Nginx."
    assert signal.metadata["is_official"] is True
    assert "container-image" in signal.tags
    assert signal.credibility > 0.8


def test_parse_repository_signal_handles_missing_optional_fields() -> None:
    signal = parse_repository_signal({}, repo_id=("example", "worker"))

    assert signal.id == "dockerhub_image_trends:example/worker"
    assert signal.title == "example/worker Docker Hub image trend"
    assert signal.content == "example/worker has 0 pulls and 0 stars on Docker Hub."
    assert signal.published_at is None
    assert signal.metadata["repository_name"] == "example/worker"
    assert signal.metadata["pull_count"] == 0
    assert signal.metadata["star_count"] == 0
    assert signal.metadata["last_updated"] is None
    assert signal.metadata["description"] == ""


@pytest.mark.asyncio
async def test_fetch_uses_configured_repositories_and_mocked_client() -> None:
    adapter = DockerHubImageTrendsAdapter(
        config={
            "repositories": [
                "_/nginx",
                {"repository": "example/api"},
                "library/nginx",
                "",
            ],
            "api_url": "https://hub.docker.test/v2",
            "timeout": 8,
        }
    )
    requests: list[dict] = []

    async def mock_request(method: str, url: str, **kwargs) -> httpx.Response:
        requests.append({"method": method, "url": url, **kwargs})
        if url.endswith("/namespaces/library/repositories/nginx"):
            return _response(MOCK_REPOSITORY)
        if url.endswith("/namespaces/example/repositories/api"):
            return _response(
                {
                    "namespace": "example",
                    "name": "api",
                    "short_description": "API image.",
                    "pull_count": 500,
                    "star_count": 7,
                }
            )
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.dockerhub_image_trends.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request = mock_request
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert mock_cls.call_args.kwargs["timeout"] == 8.0
    assert adapter.repositories == ["library/nginx", "example/api"]
    assert [request["url"] for request in requests] == [
        "https://hub.docker.test/v2/namespaces/library/repositories/nginx",
        "https://hub.docker.test/v2/namespaces/example/repositories/api",
    ]
    assert [signal.id for signal in signals] == [
        "dockerhub_image_trends:library/nginx",
        "dockerhub_image_trends:example/api",
    ]
    assert signals[1].metadata["description"] == "API image."


@pytest.mark.asyncio
async def test_fetch_skips_failed_or_malformed_repository_responses() -> None:
    adapter = DockerHubImageTrendsAdapter(
        config={
            "repositories": ["example/bad", "example/malformed", "example/ok"],
            "api_url": "https://hub.docker.test/v2",
        }
    )

    async def mock_request(method: str, url: str, **kwargs) -> httpx.Response:
        if url.endswith("/namespaces/example/repositories/bad"):
            return _response({"message": "missing"}, status_code=404)
        if url.endswith("/namespaces/example/repositories/malformed"):
            return _response(["not", "a", "dict"])
        if url.endswith("/namespaces/example/repositories/ok"):
            return _response({"namespace": "example", "name": "ok", "pull_count": 12})
        raise AssertionError(f"unexpected URL: {url}")

    with patch("max.sources.dockerhub_image_trends.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.request = mock_request
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].id == "dockerhub_image_trends:example/ok"
    assert signals[0].metadata["pull_count"] == 12


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = DockerHubImageTrendsAdapter(
        config={"repositories": ["library/nginx", "library/postgres"], "api_url": "https://hub.docker.test/v2"}
    )

    with patch("max.sources.dockerhub_image_trends.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_REPOSITORY)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert mock_fetch.call_count == 1
