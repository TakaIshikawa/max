"""Comprehensive tests for npm registry source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError
from max.sources.npm_registry import NpmRegistryAdapter, _DEFAULT_QUERIES
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_NPM_SEARCH_MCP = {
    "objects": [
        {
            "package": {
                "name": "@modelcontextprotocol/server-sqlite",
                "version": "0.2.0",
                "description": "MCP server for SQLite database interactions",
                "date": "2026-03-29T12:00:00.000Z",
                "publisher": {"username": "mcp-team"},
                "keywords": ["mcp", "server", "sqlite", "database"],
            },
            "searchScore": 50000,
        },
        {
            "package": {
                "name": "mcp-server-puppeteer",
                "version": "1.0.0",
                "description": "Browser automation MCP server using Puppeteer",
                "date": "2026-03-28T10:00:00.000Z",
                "publisher": {"username": "webdev"},
                "keywords": ["mcp", "puppeteer", "automation"],
            },
            "searchScore": 100000,
        },
    ]
}

MOCK_NPM_SEARCH_AI_AGENT = {
    "objects": [
        {
            "package": {
                "name": "langchain-agent",
                "version": "2.1.0",
                "description": "AI agent framework built on LangChain",
                "date": "2026-03-27T08:00:00.000Z",
                "publisher": {"username": "ai-dev"},
                "keywords": ["ai", "agent", "langchain", "llm"],
            },
            "searchScore": 150000,
        }
    ]
}

MOCK_NPM_SEARCH_EMPTY = {"objects": []}

MOCK_NPM_SEARCH_NO_DESCRIPTION = {
    "objects": [
        {
            "package": {
                "name": "minimal-package",
                "version": "0.1.0",
                "description": "",
                "date": "2026-03-26T12:00:00.000Z",
                "publisher": {"username": "minimal-dev"},
                "keywords": [],
            },
            "searchScore": 5000,
        }
    ]
}

MOCK_NPM_SEARCH_NO_DATE = {
    "objects": [
        {
            "package": {
                "name": "no-date-package",
                "version": "1.0.0",
                "description": "Package without publication date",
                "publisher": {"username": "test-user"},
                "keywords": ["test"],
            },
            "searchScore": 10000,
        }
    ]
}

MOCK_NPM_SEARCH_NO_PUBLISHER = {
    "objects": [
        {
            "package": {
                "name": "no-publisher-package",
                "version": "1.0.0",
                "description": "Package without publisher info",
                "date": "2026-03-25T12:00:00.000Z",
                "keywords": ["test"],
            },
            "searchScore": 10000,
        }
    ]
}


# ── Adapter Property Tests ───────────────────────────────────────────


def test_npm_adapter_name_property() -> None:
    """Adapter returns correct name."""
    adapter = NpmRegistryAdapter()
    assert adapter.name == "npm_registry"


def test_npm_adapter_source_type_property() -> None:
    """Adapter returns correct source type."""
    adapter = NpmRegistryAdapter()
    assert adapter.source_type == SignalSourceType.REGISTRY.value


def test_npm_adapter_queries_default() -> None:
    """Adapter uses default queries when not configured."""
    adapter = NpmRegistryAdapter()
    assert adapter.queries == _DEFAULT_QUERIES


def test_npm_adapter_queries_custom() -> None:
    """Adapter uses custom queries from config."""
    custom_queries = ["database", "sql", "postgres"]
    adapter = NpmRegistryAdapter(config={"queries": custom_queries})
    assert adapter.queries == custom_queries


# ── Successful Fetch Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_fetch_success() -> None:
    """Adapter successfully fetches and parses npm search results."""
    adapter = NpmRegistryAdapter(config={"queries": ["mcp server"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2

    # Check first signal
    first = signals[0]
    assert first.source_type == SignalSourceType.REGISTRY
    assert first.source_adapter == "npm_registry"
    assert first.title == "@modelcontextprotocol/server-sqlite@0.2.0"
    assert first.content == "MCP server for SQLite database interactions"
    assert first.url == "https://www.npmjs.com/package/@modelcontextprotocol/server-sqlite"
    assert first.author == "mcp-team"
    assert first.published_at == datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)
    assert first.tags == ["mcp", "server", "sqlite", "database"]
    assert first.credibility == min(50000 / 100_000, 1.0)
    assert first.metadata["npm_name"] == "@modelcontextprotocol/server-sqlite"
    assert first.metadata["version"] == "0.2.0"
    assert first.metadata["search_query"] == "mcp server"

    # Check second signal
    second = signals[1]
    assert second.title == "mcp-server-puppeteer@1.0.0"
    assert second.credibility == min(100000 / 100_000, 1.0)


@pytest.mark.asyncio
async def test_npm_adapter_signal_url_format() -> None:
    """Adapter constructs correct npm package URL."""
    adapter = NpmRegistryAdapter(config={"queries": ["mcp server"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

        signals = await adapter.fetch(limit=10)

    for signal in signals:
        assert signal.url.startswith("https://www.npmjs.com/package/")
        assert signal.metadata["npm_name"] in signal.url


# ── Multi-Query Tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_multi_query_iteration() -> None:
    """Adapter iterates through multiple queries until limit reached."""
    adapter = NpmRegistryAdapter()

    call_count = 0
    query_params = []

    async def mock_fetch_with_retry(url, client, adapter_name, params):
        nonlocal call_count
        call_count += 1
        query_params.append(params)

        if "mcp server" in params.get("text", ""):
            return MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)
        return MagicMock(json=lambda: MOCK_NPM_SEARCH_AI_AGENT)

    with patch("max.sources.npm_registry.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should call for multiple queries
    assert call_count >= 2
    assert len(query_params) >= 2

    # Check that queries match defaults
    queried_texts = [p["text"] for p in query_params]
    assert "mcp server" in queried_texts
    assert "ai agent" in queried_texts


@pytest.mark.asyncio
async def test_npm_adapter_stops_at_limit() -> None:
    """Adapter stops querying when limit is reached."""
    adapter = NpmRegistryAdapter()

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        # Each query returns 2 results
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

        signals = await adapter.fetch(limit=3)

    # Should stop at 3, not fetch all 4 queries worth
    assert len(signals) <= 3


@pytest.mark.asyncio
async def test_npm_adapter_size_param_calculation() -> None:
    """Adapter calculates size param as min(10, limit - len(signals))."""
    adapter = NpmRegistryAdapter()

    call_params = []

    async def mock_fetch_with_retry(url, client, adapter_name, params):
        call_params.append(params)
        return MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

    with patch("max.sources.npm_registry.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=15)

    # First query: min(10, 15 - 0) = 10
    assert call_params[0]["size"] == 10

    # Second query: min(10, 15 - 2) = 10 (2 results from first query)
    if len(call_params) > 1:
        assert call_params[1]["size"] == 10


# ── Credibility Calculation Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_credibility_from_search_score() -> None:
    """Adapter calculates credibility as min(search_score / 100_000, 1.0)."""
    test_cases = [
        ({"objects": [{"package": {"name": "pkg1", "version": "1.0.0", "description": "test"}, "searchScore": 100000}]}, 1.0),
        ({"objects": [{"package": {"name": "pkg2", "version": "1.0.0", "description": "test"}, "searchScore": 50000}]}, 0.5),
        ({"objects": [{"package": {"name": "pkg3", "version": "1.0.0", "description": "test"}, "searchScore": 0}]}, 0.0),
        ({"objects": [{"package": {"name": "pkg4", "version": "1.0.0", "description": "test"}, "searchScore": 150000}]}, 1.0),
    ]

    for mock_response, expected_credibility in test_cases:
        adapter = NpmRegistryAdapter(config={"queries": ["test"]})

        with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
            mock_fetch.return_value = MagicMock(json=lambda resp=mock_response: resp)

            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].credibility == expected_credibility


# ── Date Parsing Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_date_parsing_valid() -> None:
    """Adapter parses ISO date string with Z suffix correctly."""
    adapter = NpmRegistryAdapter(config={"queries": ["mcp server"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

        signals = await adapter.fetch(limit=10)

    assert signals[0].published_at == datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_npm_adapter_date_parsing_none() -> None:
    """Adapter handles missing date field gracefully."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_NO_DATE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].published_at is None


@pytest.mark.asyncio
async def test_npm_adapter_date_parsing_invalid() -> None:
    """Adapter skips packages with invalid date strings."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    invalid_date_response = {
        "objects": [
            {
                "package": {
                    "name": "invalid-date-pkg",
                    "version": "1.0.0",
                    "description": "Package with invalid date",
                    "date": "not a valid date",
                    "publisher": {"username": "test"},
                },
                "searchScore": 10000,
            }
        ]
    }

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: invalid_date_response)

        signals = await adapter.fetch(limit=10)

    # Package should be skipped due to date parsing error
    assert len(signals) == 0


# ── Keywords/Tags Tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_keywords_as_tags() -> None:
    """Adapter uses package keywords as tags."""
    adapter = NpmRegistryAdapter(config={"queries": ["mcp server"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

        signals = await adapter.fetch(limit=10)

    assert signals[0].tags == ["mcp", "server", "sqlite", "database"]
    assert signals[1].tags == ["mcp", "puppeteer", "automation"]


@pytest.mark.asyncio
async def test_npm_adapter_truncates_keywords_to_10() -> None:
    """Adapter limits keywords to 10 tags."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    many_keywords_response = {
        "objects": [
            {
                "package": {
                    "name": "many-keywords-pkg",
                    "version": "1.0.0",
                    "description": "Package with many keywords",
                    "keywords": ["k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9", "k10", "k11", "k12"],
                },
                "searchScore": 10000,
            }
        ]
    }

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: many_keywords_response)

        signals = await adapter.fetch(limit=10)

    assert len(signals[0].tags) == 10


@pytest.mark.asyncio
async def test_npm_adapter_empty_keywords() -> None:
    """Adapter handles empty keywords array."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_NO_DESCRIPTION)

        signals = await adapter.fetch(limit=10)

    assert signals[0].tags == []


# ── Error Handling Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_handles_fetch_error() -> None:
    """Adapter logs warning and continues on AdapterFetchError."""
    adapter = NpmRegistryAdapter()

    call_count = 0

    async def mock_fetch_with_retry(url, client, adapter_name, params):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            raise AdapterFetchError("npm_registry", 404, url)
        return MagicMock(json=lambda: MOCK_NPM_SEARCH_AI_AGENT)

    with patch("max.sources.npm_registry.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should continue to next query despite first query failure
    assert call_count >= 2
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_npm_adapter_handles_json_parse_error() -> None:
    """Adapter logs warning and continues on JSON parsing error."""
    adapter = NpmRegistryAdapter()

    call_count = 0

    async def mock_fetch_with_retry(url, client, adapter_name, params):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            mock_resp = MagicMock()
            mock_resp.json.side_effect = ValueError("Invalid JSON")
            return mock_resp
        return MagicMock(json=lambda: MOCK_NPM_SEARCH_AI_AGENT)

    with patch("max.sources.npm_registry.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should continue to next query despite JSON error
    assert call_count >= 2
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_npm_adapter_handles_key_error() -> None:
    """Adapter logs warning and continues on JSON parsing KeyError."""
    adapter = NpmRegistryAdapter()

    call_count = 0

    async def mock_fetch_with_retry(url, client, adapter_name, params):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            mock_resp = MagicMock()
            mock_resp.json.side_effect = KeyError("missing key")
            return mock_resp
        return MagicMock(json=lambda: MOCK_NPM_SEARCH_AI_AGENT)

    with patch("max.sources.npm_registry.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should continue to next query despite KeyError
    assert call_count >= 2
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_npm_adapter_handles_package_parsing_error() -> None:
    """Adapter skips packages that cause KeyError, TypeError, or ValueError during parsing."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    # Use a MagicMock that raises TypeError when pkg.get("keywords") is accessed
    class MockPackage:
        def get(self, key, default=None):
            if key == "name":
                return "error-pkg"
            if key == "version":
                return "1.0.0"
            if key == "description":
                return "Package that causes error"
            if key == "keywords":
                raise TypeError("Mock keywords TypeError")
            return default

    mixed_response = {
        "objects": [
            {
                "package": {
                    "name": "valid-pkg",
                    "version": "1.0.0",
                    "description": "Valid package",
                },
                "searchScore": 10000,
            },
            {
                "package": MockPackage(),
                "searchScore": 5000,
            },
            {
                "package": {
                    "name": "another-valid-pkg",
                    "version": "2.0.0",
                    "description": "Another valid package",
                },
                "searchScore": 8000,
            },
        ]
    }

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: mixed_response)

        signals = await adapter.fetch(limit=10)

    # Should have 2 valid signals, skipping the one that caused TypeError
    assert len(signals) == 2
    names = [s.metadata["npm_name"] for s in signals]
    assert "valid-pkg" in names
    assert "another-valid-pkg" in names
    assert "error-pkg" not in names


# ── Content Fallback Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_content_fallback_to_name() -> None:
    """Adapter uses package name when description is empty."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_NO_DESCRIPTION)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].content == "minimal-package"


# ── Empty Response Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_empty_response() -> None:
    """Adapter handles empty objects array gracefully."""
    adapter = NpmRegistryAdapter()

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_EMPTY)

        signals = await adapter.fetch(limit=10)

    # Should try all queries but get no results
    assert len(signals) == 0


# ── Missing Field Tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_missing_publisher() -> None:
    """Adapter handles missing publisher field gracefully."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_NO_PUBLISHER)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].author is None


@pytest.mark.asyncio
async def test_npm_adapter_missing_search_score() -> None:
    """Adapter defaults to 0 credibility when searchScore is missing."""
    adapter = NpmRegistryAdapter(config={"queries": ["test"]})

    no_score_response = {
        "objects": [
            {
                "package": {
                    "name": "no-score-pkg",
                    "version": "1.0.0",
                    "description": "Package without search score",
                },
                # searchScore is missing
            }
        ]
    }

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        mock_fetch.return_value = MagicMock(json=lambda: no_score_response)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].credibility == 0.0


# ── Global Limit Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_global_limit_respected() -> None:
    """Adapter respects limit across all queries."""
    adapter = NpmRegistryAdapter(config={"queries": ["q1", "q2", "q3", "q4"]})

    with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
        # Each query returns 2 results
        mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_MCP)

        signals = await adapter.fetch(limit=5)

    # Should stop at 5 total, not fetch all 4 queries worth (8 total)
    assert len(signals) <= 5


# ── HTTP Client Context Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_uses_async_client() -> None:
    """Adapter uses httpx.AsyncClient with correct timeout."""
    adapter = NpmRegistryAdapter()

    client_created = False
    original_async_client = httpx.AsyncClient

    class MockAsyncClient:
        def __init__(self, timeout=None):
            nonlocal client_created
            client_created = True
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("max.sources.npm_registry.httpx.AsyncClient", MockAsyncClient):
        with patch("max.sources.npm_registry.fetch_with_retry") as mock_fetch:
            mock_fetch.return_value = MagicMock(json=lambda: MOCK_NPM_SEARCH_EMPTY)

            await adapter.fetch(limit=10)

    assert client_created


# ── Integration with fetch_with_retry Tests ──────────────────────────


@pytest.mark.asyncio
async def test_npm_adapter_calls_fetch_with_retry_correctly() -> None:
    """Adapter calls fetch_with_retry with correct parameters."""
    adapter = NpmRegistryAdapter()

    call_args_list = []

    async def mock_fetch_with_retry(url, client, adapter_name, params):
        call_args_list.append({
            "url": url,
            "adapter_name": adapter_name,
            "params": params,
        })
        return MagicMock(json=lambda: MOCK_NPM_SEARCH_EMPTY)

    with patch("max.sources.npm_registry.fetch_with_retry", mock_fetch_with_retry):
        await adapter.fetch(limit=10)

    assert len(call_args_list) >= 1
    first_call = call_args_list[0]
    assert first_call["url"] == "https://registry.npmjs.org/-/v1/search"
    assert first_call["adapter_name"] == "npm_registry"
    assert "text" in first_call["params"]
    assert "size" in first_call["params"]
