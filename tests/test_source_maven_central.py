"""Tests for the Maven Central source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from max.sources.maven_central import MavenCentralAdapter, _DEFAULT_COORDINATES, _DEFAULT_QUERIES
from max.types.signal import SignalSourceType


MOCK_COORDINATE_SEARCH = {
    "response": {
        "docs": [
            {
                "id": "dev.langchain4j:langchain4j",
                "g": "dev.langchain4j",
                "a": "langchain4j",
                "latestVersion": "1.0.0",
                "repositoryId": "central",
                "p": "jar",
                "timestamp": 1776688200000,
                "versionCount": 86,
                "text": ["dev.langchain4j", "langchain4j", "jar"],
                "tags": ["ai", "llm"],
            }
        ]
    }
}

MOCK_QUERY_SEARCH = {
    "response": {
        "docs": [
            {
                "id": "org.springframework.ai:spring-ai-core",
                "g": "org.springframework.ai",
                "a": "spring-ai-core",
                "latestVersion": "1.0.0-M8",
                "repositoryId": "central",
                "p": "jar",
                "timestamp": 1773561600000,
                "versionCount": 24,
                "text": ["Spring AI core abstractions"],
                "tags": ["spring", "ai"],
            },
            {
                "id": "com.example:agent-runtime",
                "g": "com.example",
                "a": "agent-runtime",
                "latestVersion": "2.1.0",
                "repositoryId": "central",
                "p": "pom",
                "timestamp": 1776762000000,
                "versionCount": 4,
                "text": ["agent runtime"],
            },
        ]
    }
}

MOCK_MALFORMED_SEARCH = {
    "response": {
        "docs": [
            {"g": "missing.artifact", "latestVersion": "1.0.0"},
            {"a": "missing-group", "latestVersion": "1.0.0"},
            "not-a-doc",
            {
                "g": "valid.group",
                "a": "valid-artifact",
                "latestVersion": "0.1.0",
                "timestamp": "not-a-timestamp",
                "versionCount": None,
            },
        ]
    }
}


def test_maven_central_adapter_properties() -> None:
    adapter = MavenCentralAdapter()

    assert adapter.name == "maven_central"
    assert adapter.source_type == SignalSourceType.REGISTRY.value
    assert adapter.queries == _DEFAULT_QUERIES
    assert adapter.coordinates == _DEFAULT_COORDINATES


def test_maven_central_adapter_custom_config() -> None:
    adapter = MavenCentralAdapter(
        config={
            "queries": ["semantic kernel"],
            "coordinates": ["org.springframework.ai:spring-ai-core"],
            "watchlist_terms": ["mcp"],
        }
    )

    assert adapter.queries == ["semantic kernel", "mcp"]
    assert adapter.coordinates == ["org.springframework.ai:spring-ai-core", "mcp"]


@pytest.mark.asyncio
async def test_maven_central_fetches_configured_coordinates() -> None:
    adapter = MavenCentralAdapter(
        config={"queries": [], "coordinates": ["dev.langchain4j:langchain4j"]}
    )

    with patch("max.sources.maven_central.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_COORDINATE_SEARCH)

        signals = await adapter.fetch(limit=5)

    assert len(signals) == 1
    assert mock_fetch.call_args.kwargs["params"] == {
        "q": 'g:"dev.langchain4j" AND a:"langchain4j"',
        "rows": 1,
        "wt": "json",
    }

    signal = signals[0]
    assert signal.source_type == SignalSourceType.REGISTRY
    assert signal.source_adapter == "maven_central"
    assert signal.title == "dev.langchain4j:langchain4j@1.0.0"
    assert signal.content == "dev.langchain4j langchain4j jar"
    assert signal.url == "https://central.sonatype.com/artifact/dev.langchain4j/langchain4j"
    assert signal.author == "dev.langchain4j"
    assert signal.published_at == datetime(2026, 4, 20, 12, 30, tzinfo=timezone.utc)
    assert signal.tags == ["jar", "ai", "llm"]
    assert signal.metadata["package_ecosystem"] == "maven"
    assert signal.metadata["package_id"] == "dev.langchain4j:langchain4j"
    assert signal.metadata["group_id"] == "dev.langchain4j"
    assert signal.metadata["artifact_id"] == "langchain4j"
    assert signal.metadata["latest_version"] == "1.0.0"
    assert signal.metadata["version_count"] == 86
    assert signal.metadata["repository_url"] == (
        "https://repo1.maven.org/maven2/dev/langchain4j/langchain4j/1.0.0/"
    )
    assert signal.metadata["source_url"] == signal.url
    assert signal.metadata["coordinate"] == "dev.langchain4j:langchain4j"
    assert signal.metadata["search_query"] is None


@pytest.mark.asyncio
async def test_maven_central_fetches_query_results() -> None:
    adapter = MavenCentralAdapter(config={"queries": ["spring ai"], "coordinates": []})

    with patch("max.sources.maven_central.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_QUERY_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2
    assert mock_fetch.call_args.kwargs["params"] == {"q": "spring ai", "rows": 10, "wt": "json"}
    assert signals[0].title == "org.springframework.ai:spring-ai-core@1.0.0-M8"
    assert signals[0].tags == ["jar", "spring", "ai", "spring ai"]
    assert signals[0].metadata["search_query"] == "spring ai"
    assert signals[0].metadata["coordinate"] is None
    assert signals[1].title == "com.example:agent-runtime@2.1.0"
    assert signals[1].metadata["packaging"] == "pom"


@pytest.mark.asyncio
async def test_maven_central_skips_malformed_records() -> None:
    adapter = MavenCentralAdapter(config={"queries": ["valid"], "coordinates": []})

    with patch("max.sources.maven_central.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_MALFORMED_SEARCH)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "valid.group:valid-artifact@0.1.0"
    assert signal.content == "valid.group:valid-artifact"
    assert signal.published_at is None
    assert signal.metadata["version_count"] == 0
    assert signal.metadata["repository_url"] == (
        "https://repo1.maven.org/maven2/valid/group/valid-artifact/0.1.0/"
    )


@pytest.mark.asyncio
async def test_maven_central_suppresses_duplicate_group_artifact_pairs() -> None:
    adapter = MavenCentralAdapter(
        config={"queries": ["langchain4j"], "coordinates": ["dev.langchain4j:langchain4j"]}
    )

    with patch("max.sources.maven_central.fetch_with_retry") as mock_fetch:
        mock_fetch.side_effect = [
            MagicMock(json=lambda: MOCK_COORDINATE_SEARCH),
            MagicMock(json=lambda: MOCK_COORDINATE_SEARCH),
        ]

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].metadata["package_id"] == "dev.langchain4j:langchain4j"
    assert mock_fetch.call_count == 2


@pytest.mark.asyncio
async def test_maven_central_respects_limit() -> None:
    adapter = MavenCentralAdapter(config={"queries": ["ai"], "coordinates": []})

    with patch("max.sources.maven_central.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_QUERY_SEARCH)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1
    assert signals[0].metadata["package_id"] == "org.springframework.ai:spring-ai-core"
    assert mock_fetch.call_args.kwargs["params"] == {"q": "ai", "rows": 1, "wt": "json"}
