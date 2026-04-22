"""Tests for the Docker Hub source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.dockerhub import DockerHubAdapter, _DEFAULT_QUERIES, _DEFAULT_REPOSITORIES
from max.types.signal import SignalSourceType


MOCK_REPOSITORY = {
    "user": "library",
    "name": "nginx",
    "namespace": "library",
    "repository_type": "image",
    "description": "Official build of Nginx.",
    "is_automated": False,
    "is_official": True,
    "star_count": 20000,
    "pull_count": 1_500_000_000,
    "last_updated": "2026-04-20T12:30:00Z",
    "categories": [{"name": "Web servers"}, {"slug": "networking"}],
}

MOCK_TAGS = {
    "results": [
        {"name": "latest", "last_updated": "2026-04-21T09:00:00Z"},
        {"name": "alpine", "last_updated": "2026-04-19T08:00:00Z"},
    ]
}

MOCK_SEARCH = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "repo_name": "ollama/ollama",
            "short_description": "Get up and running with large language models.",
            "star_count": 1200,
            "pull_count": 80_000_000,
            "repo_owner": "ollama",
            "is_automated": False,
            "is_official": False,
        }
    ],
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


def test_dockerhub_adapter_properties() -> None:
    adapter = DockerHubAdapter()

    assert adapter.name == "dockerhub"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.repositories == _DEFAULT_REPOSITORIES
    assert adapter.include_tags is True


def test_dockerhub_adapter_custom_config() -> None:
    adapter = DockerHubAdapter(
        config={
            "queries": ["vector database"],
            "repositories": ["ollama/ollama"],
            "watchlist_terms": ["mcp"],
            "include_tags": False,
        }
    )

    assert adapter.queries == ["vector database", "mcp"]
    assert adapter.repositories == ["ollama/ollama", "mcp"]
    assert adapter.include_tags is False


@pytest.mark.asyncio
async def test_dockerhub_fetches_configured_repository_with_tags() -> None:
    adapter = DockerHubAdapter(config={"repositories": ["_/nginx"], "queries": []})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_REPOSITORY),
            MagicMock(json=lambda: MOCK_TAGS),
        ]

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert "namespaces/library/repositories/nginx" in mock_fetch.call_args_list[0].args[0]
    assert "namespaces/library/repositories/nginx/tags" in mock_fetch.call_args_list[1].args[0]

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "dockerhub"
    assert signal.title == "library/nginx"
    assert signal.content == "Official build of Nginx."
    assert signal.url == "https://hub.docker.com/_/nginx"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == ["Web servers", "networking", "latest", "alpine"]
    assert signal.credibility > 0.8
    assert signal.metadata["repository_name"] == "library/nginx"
    assert signal.metadata["description"] == "Official build of Nginx."
    assert signal.metadata["star_count"] == 20000
    assert signal.metadata["pull_count"] == 1_500_000_000
    assert signal.metadata["last_updated"] == "2026-04-20T12:30:00+00:00"
    assert signal.metadata["categories"] == ["Web servers", "networking"]
    assert signal.metadata["tags"] == ["latest", "alpine"]
    assert signal.metadata["is_official"] is True


@pytest.mark.asyncio
async def test_dockerhub_fetches_keyword_search_and_merges_detail() -> None:
    adapter = DockerHubAdapter(config={"repositories": [], "queries": ["llm"]})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(json=lambda: MOCK_SEARCH_DETAIL),
            MagicMock(json=lambda: MOCK_TAGS),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert mock_fetch.call_args_list[0].args[0].endswith("/v2/search/repositories/")
    assert mock_fetch.call_args_list[0].kwargs["params"] == {"query": "llm", "page_size": 10}

    signal = signals[0]
    assert signal.title == "ollama/ollama"
    assert signal.content == "Run LLMs in containers."
    assert signal.url == "https://hub.docker.com/r/ollama/ollama"
    assert signal.published_at == datetime(2026, 4, 18, 10, 15, tzinfo=timezone.utc)
    assert signal.tags == ["Machine learning & AI", "latest", "alpine", "llm"]
    assert signal.metadata["star_count"] == 1300
    assert signal.metadata["pull_count"] == 90_000_000
    assert signal.metadata["search_query"] == "llm"
    assert signal.metadata["is_official"] is False


@pytest.mark.asyncio
async def test_dockerhub_uses_search_result_when_detail_fails() -> None:
    adapter = DockerHubAdapter(config={"repositories": [], "queries": ["llm"], "include_tags": False})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_SEARCH),
            MagicMock(status_code=404, json=lambda: {}),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "ollama/ollama"
    assert signal.content == "Get up and running with large language models."
    assert signal.published_at is None
    assert signal.tags == ["llm"]
    assert signal.metadata["star_count"] == 1200
    assert signal.metadata["pull_count"] == 80_000_000


@pytest.mark.asyncio
async def test_dockerhub_respects_limit_and_dedupes_repositories() -> None:
    adapter = DockerHubAdapter(config={"repositories": ["library/nginx"], "queries": ["nginx"]})

    with patch("max.sources.dockerhub.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_REPOSITORY),
            MagicMock(json=lambda: MOCK_TAGS),
        ]

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["repository_name"] == "library/nginx"
    assert mock_fetch.call_count == 2
