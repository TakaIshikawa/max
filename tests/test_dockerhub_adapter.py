"""Tests for Docker Hub import adapter — container image signal collection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.dockerhub_adapter import (
    DockerHubAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_SEARCH_RESPONSE = {
    "results": [
        {
            "repo_name": "library/python",
            "short_description": "Python is an interpreted, interactive, object-oriented programming language.",
            "pull_count": 2_000_000_000,
            "star_count": 8500,
            "is_official": True,
            "is_automated": False,
            "last_updated": "2024-01-20T10:00:00Z",
        },
        {
            "repo_name": "library/node",
            "short_description": "Node.js is a JavaScript-based platform for server-side and networking applications.",
            "pull_count": 1_500_000_000,
            "star_count": 7200,
            "is_official": True,
            "is_automated": False,
            "last_updated": "2024-01-19T08:00:00Z",
        },
    ],
}

MOCK_NAMESPACED_RESPONSE = {
    "results": [
        {
            "repo_name": "bitnami/postgresql",
            "short_description": "Bitnami PostgreSQL Docker Image",
            "pull_count": 500_000_000,
            "star_count": 200,
            "is_official": False,
            "is_automated": True,
            "last_updated": "2024-01-18T06:00:00Z",
        },
    ],
}

MOCK_EMPTY_RESPONSE = {"results": []}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2024-01-15T10:00:00Z")
    assert dt is not None
    assert dt.year == 2024


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_build_tags_official() -> None:
    tags = _build_tags("python", "library")
    assert "docker" in tags
    assert "container" in tags
    assert "official" in tags
    assert "python" in tags


def test_build_tags_database() -> None:
    tags = _build_tags("postgres", "library")
    assert "database" in tags


def test_build_tags_non_official() -> None:
    tags = _build_tags("myapp", "bitnami")
    assert "docker" in tags
    assert "official" not in tags


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = DockerHubAdapter()
    assert adapter.name == "dockerhub_import"


def test_adapter_source_type() -> None:
    adapter = DockerHubAdapter()
    assert adapter.source_type == SignalSourceType.REGISTRY.value


def test_adapter_default_search_terms() -> None:
    adapter = DockerHubAdapter()
    assert "python" in adapter.search_terms
    assert "node" in adapter.search_terms


def test_adapter_custom_search_terms() -> None:
    adapter = DockerHubAdapter(config={"search_terms": ["redis", "nginx"]})
    assert adapter.search_terms == ["redis", "nginx"]


def test_adapter_query() -> None:
    adapter = DockerHubAdapter(config={"query": "python"})
    assert adapter.query == "python"


# ── Fetch tests with mocked API ──────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_search_images() -> None:
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    sig = signals[0]
    assert sig.title == "library/python"
    assert sig.source_adapter == "dockerhub_import"
    assert sig.source_type == SignalSourceType.REGISTRY
    assert "docker" in sig.tags
    assert sig.metadata["pull_count"] == 2_000_000_000
    assert sig.metadata["star_count"] == 8500
    assert sig.metadata["is_official"] is True


@pytest.mark.asyncio
async def test_fetch_with_query() -> None:
    adapter = DockerHubAdapter(config={"query": "postgresql"})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_NAMESPACED_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "bitnami/postgresql"
    assert signals[0].metadata["namespace"] == "bitnami"


@pytest.mark.asyncio
async def test_fetch_url_official() -> None:
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        # Use namespaced response where repo_name has no slash for official
        official_resp = {
            "results": [{
                "repo_name": "python",
                "short_description": "Python",
                "pull_count": 100,
                "star_count": 10,
                "is_official": True,
                "is_automated": False,
            }],
        }
        mock_fetch.return_value = _mock_response(official_resp)
        signals = await adapter.fetch(limit=10)

    assert signals[0].url == "https://hub.docker.com/_/python"


@pytest.mark.asyncio
async def test_fetch_url_namespaced() -> None:
    adapter = DockerHubAdapter(config={"query": "postgresql"})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_NAMESPACED_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals[0].url == "https://hub.docker.com/r/bitnami/postgresql"


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)
        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates() -> None:
    dup_response = {
        "results": [MOCK_SEARCH_RESPONSE["results"][0], MOCK_SEARCH_RESPONSE["results"][0]],
    }
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)
        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_credibility_capped() -> None:
    high_pull = {
        "results": [{
            **MOCK_SEARCH_RESPONSE["results"][0],
            "pull_count": 5_000_000_000,
        }],
    }
    adapter = DockerHubAdapter(config={"search_terms": ["python"]})

    with patch(
        "max.imports.dockerhub_adapter.fetch_with_retry",
        new_callable=AsyncMock,
    ) as mock_fetch:
        mock_fetch.return_value = _mock_response(high_pull)
        signals = await adapter.fetch(limit=10)

    assert signals[0].credibility == 1.0
