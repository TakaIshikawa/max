"""Tests for the Docker Hub repository activity source adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from max.sources.docker_hub import DockerHubAdapter
from max.types.signal import SignalSourceType


MOCK_NGINX = {
    "namespace": "library",
    "name": "nginx",
    "description": "Official build of Nginx.",
    "star_count": 20000,
    "pull_count": 1_500_000_000,
    "last_updated": "2026-04-20T12:30:00Z",
    "categories": [{"name": "Web servers"}, {"slug": "networking"}],
    "is_official": True,
}

MOCK_REDIS = {
    "namespace": "library",
    "name": "redis",
    "description": "Official Redis image.",
    "star_count": 12000,
    "pull_count": 900_000_000,
    "last_updated": "2026-04-19T08:00:00Z",
}

MOCK_TAGS = {
    "results": [
        {"name": "latest", "last_updated": "2026-04-21T09:00:00Z"},
        {"name": "alpine", "last_updated": "2026-04-19T08:00:00Z"},
        "malformed",
    ]
}

MOCK_SEARCH = {
    "results": [
        {
            "repo_name": "ollama/ollama",
            "short_description": "Get up and running with large language models.",
            "star_count": 1200,
            "pull_count": 80_000_000,
        },
        {"name": None},
        "malformed",
    ]
}

MOCK_SEARCH_DETAIL = {
    "name": "ollama",
    "namespace": "ollama",
    "description": "Run LLMs in containers.",
    "star_count": 1300,
    "pull_count": 90_000_000,
    "last_updated": "2026-04-18T10:15:00Z",
    "categories": ["Machine learning & AI"],
}


@pytest.mark.asyncio
async def test_docker_hub_converts_repository_response_to_signal() -> None:
    adapter = DockerHubAdapter(config={"repositories": ["_/nginx"], "queries": []})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_NGINX),
            MagicMock(json=lambda: MOCK_TAGS),
        ]

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.id.startswith("docker_hub:")
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "docker_hub"
    assert signal.title == "library/nginx"
    assert signal.content == "Official build of Nginx."
    assert signal.url == "https://hub.docker.com/_/nginx"
    assert signal.tags == ["Web servers", "networking", "latest", "alpine"]
    assert signal.metadata["repository_name"] == "library/nginx"
    assert signal.metadata["star_count"] == 20000
    assert signal.metadata["pull_count"] == 1_500_000_000
    assert signal.metadata["is_official"] is True
    assert signal.credibility > 0.8


@pytest.mark.asyncio
async def test_docker_hub_fetches_multiple_configured_repositories() -> None:
    adapter = DockerHubAdapter(
        config={"repositories": ["library/nginx", "library/redis"], "queries": [], "include_tags": False}
    )

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_NGINX),
            MagicMock(json=lambda: MOCK_REDIS),
        ]

        signals = await adapter.fetch(limit=10)

    assert [signal.title for signal in signals] == ["library/nginx", "library/redis"]
    assert [signal.metadata["pull_count"] for signal in signals] == [1_500_000_000, 900_000_000]


@pytest.mark.asyncio
async def test_docker_hub_search_merges_detail_and_skips_malformed_records() -> None:
    adapter = DockerHubAdapter(config={"repositories": [], "queries": ["llm"]})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(json=lambda: MOCK_SEARCH_DETAIL),
            MagicMock(json=lambda: MOCK_TAGS),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "ollama/ollama"
    assert signal.content == "Run LLMs in containers."
    assert signal.tags == ["Machine learning & AI", "latest", "alpine", "llm"]
    assert signal.metadata["search_query"] == "llm"
    assert signal.metadata["star_count"] == 1300


@pytest.mark.asyncio
async def test_docker_hub_signal_ids_are_deterministic() -> None:
    adapter = DockerHubAdapter(config={"repositories": ["library/nginx"], "queries": [], "include_tags": False})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NGINX)
        first = await adapter.fetch(limit=5)
        second = await adapter.fetch(limit=5)

    assert [signal.id for signal in first] == [signal.id for signal in second]


@pytest.mark.asyncio
async def test_docker_hub_handles_malformed_and_empty_responses_without_crashing(caplog) -> None:
    adapter = DockerHubAdapter(config={"repositories": [], "queries": ["missing"]})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: [])

        signals = await adapter.fetch(limit=5)

    assert signals == []
    assert "malformed Docker Hub response" in caplog.text


@pytest.mark.asyncio
async def test_docker_hub_handles_request_failures_without_crashing(caplog) -> None:
    adapter = DockerHubAdapter(config={"repositories": ["library/nginx"], "queries": []})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = httpx.TimeoutException("timed out")

        signals = await adapter.fetch(limit=5)

    assert signals == []
    assert "request failed for Docker Hub data" in caplog.text
