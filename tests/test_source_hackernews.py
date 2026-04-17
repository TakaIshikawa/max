"""Comprehensive tests for HackerNews source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import (
    AdapterCircuitOpenError,
    AdapterFetchError,
    AdapterRateLimitError,
)
from max.sources.errors import SourceParseError
from max.sources.hackernews import HackerNewsAdapter, _extract_tags
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_HN_TOP_STORIES = [41001, 41002, 41003, 41004, 41005]

MOCK_HN_STORY_41001 = {
    "by": "techuser",
    "descendants": 125,
    "id": 41001,
    "score": 450,
    "time": 1712188800,  # 2024-04-04 00:00:00 UTC
    "title": "Show HN: New MCP server for SQLite with Claude integration",
    "type": "story",
    "url": "https://github.com/example/mcp-sqlite",
}

MOCK_HN_STORY_41002 = {
    "by": "airesearcher",
    "descendants": 89,
    "id": 41002,
    "score": 750,
    "time": 1712275200,  # 2024-04-05 00:00:00 UTC
    "title": "Building AI agents with GPT-4 and LangChain",
    "type": "story",
    "url": "https://example.com/ai-agents",
}

MOCK_HN_STORY_41003 = {
    "by": "rustdev",
    "descendants": 45,
    "id": 41003,
    "score": 200,
    "time": 1712361600,  # 2024-04-06 00:00:00 UTC
    "title": "Rust compiler optimization techniques",
    "type": "story",
    "url": "https://rust-blog.example.com/optimization",
}

MOCK_HN_STORY_NO_URL = {
    "by": "askhnuser",
    "descendants": 30,
    "id": 41004,
    "score": 100,
    "time": 1712448000,  # 2024-04-07 00:00:00 UTC
    "title": "Ask HN: What are your favorite MCP servers?",
    "type": "story",
    # No url field — should fall back to HN item URL
}

MOCK_HN_STORY_NO_AUTHOR = {
    "descendants": 10,
    "id": 41005,
    "score": 50,
    "time": 1712534400,  # 2024-04-08 00:00:00 UTC
    "title": "Security vulnerability in popular npm package",
    "type": "story",
    "url": "https://security.example.com/vuln",
    # No by field
}

MOCK_HN_STORY_NOT_STORY_TYPE = {
    "by": "commenter",
    "id": 41006,
    "text": "This is a comment, not a story",
    "type": "comment",
}

MOCK_HN_STORY_MISSING_FIELDS = {
    "id": 41007,
    "type": "story",
    # Missing title, score, time
}

MOCK_HN_STORY_HIGH_SCORE = {
    "by": "popular",
    "descendants": 500,
    "id": 41008,
    "score": 1000,  # Very high score — credibility should cap at 1.0
    "time": 1712620800,
    "title": "Show HN: Revolutionary new programming language",
    "type": "story",
    "url": "https://newlang.example.com",
}


# ── Adapter Property Tests ───────────────────────────────────────────


def test_hackernews_adapter_name_property() -> None:
    """Adapter returns correct name."""
    adapter = HackerNewsAdapter()
    assert adapter.name == "hackernews"


def test_hackernews_adapter_source_type_property() -> None:
    """Adapter returns correct source type."""
    adapter = HackerNewsAdapter()
    assert adapter.source_type == SignalSourceType.FORUM.value


def test_hackernews_adapter_filter_keywords_default() -> None:
    """Adapter returns empty list when no filter_keywords configured."""
    adapter = HackerNewsAdapter()
    assert adapter.filter_keywords == []


def test_hackernews_adapter_filter_keywords_custom() -> None:
    """Adapter uses custom filter_keywords from config."""
    keywords = ["ai", "mcp", "rust"]
    adapter = HackerNewsAdapter(config={"filter_keywords": keywords})
    assert adapter.filter_keywords == keywords


# ── Successful Fetch Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_fetch_success() -> None:
    """Adapter successfully fetches and parses HN stories."""
    adapter = HackerNewsAdapter()

    call_count = 0

    async def mock_fetch_with_retry(url, client, adapter_name):
        nonlocal call_count
        call_count += 1

        if "topstories.json" in url:
            return MagicMock(json=lambda: MOCK_HN_TOP_STORIES[:3])
        elif "item/41001.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41001)
        elif "item/41002.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41002)
        elif "item/41003.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41003)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=3)

    assert len(signals) == 3

    # Check first signal
    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "hackernews"
    assert first.title == "Show HN: New MCP server for SQLite with Claude integration"
    assert first.content == "Show HN: New MCP server for SQLite with Claude integration"
    assert first.url == "https://github.com/example/mcp-sqlite"
    assert first.author == "techuser"
    assert first.published_at == datetime(2024, 4, 4, 0, 0, tzinfo=timezone.utc)
    assert first.credibility == min(450 / 500, 1.0)
    assert first.metadata["hn_id"] == 41001
    assert first.metadata["score"] == 450
    assert first.metadata["descendants"] == 125
    assert "mcp" in first.tags

    # Check second signal
    second = signals[1]
    assert second.title == "Building AI agents with GPT-4 and LangChain"
    assert second.credibility == min(750 / 500, 1.0)
    assert "ai" in second.tags


@pytest.mark.asyncio
async def test_hackernews_adapter_no_url_fallback() -> None:
    """Adapter falls back to HN item URL when story has no url field."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41004])
        elif "item/41004.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_NO_URL)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].url == "https://news.ycombinator.com/item?id=41004"


@pytest.mark.asyncio
async def test_hackernews_adapter_missing_author() -> None:
    """Adapter handles missing author field gracefully."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41005])
        elif "item/41005.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_NO_AUTHOR)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].author is None


@pytest.mark.asyncio
async def test_hackernews_adapter_skips_non_story_types() -> None:
    """Adapter skips items that are not type 'story'."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41006, 41001])
        elif "item/41006.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_NOT_STORY_TYPE)
        elif "item/41001.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41001)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should only have 1 signal, skipping the comment
    assert len(signals) == 1
    assert signals[0].title == "Show HN: New MCP server for SQLite with Claude integration"


@pytest.mark.asyncio
async def test_hackernews_adapter_skips_null_items() -> None:
    """Adapter skips null/empty items."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [99999, 41001])
        elif "item/99999.json" in url:
            return MagicMock(json=lambda: None)  # Dead item
        elif "item/41001.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41001)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].title == "Show HN: New MCP server for SQLite with Claude integration"


# ── Credibility Calculation Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_credibility_from_score() -> None:
    """Adapter calculates credibility as min(score / 500, 1.0)."""
    test_cases = [
        (MOCK_HN_STORY_41001, min(450 / 500, 1.0)),  # 0.9
        (MOCK_HN_STORY_41002, min(750 / 500, 1.0)),  # 1.0 (capped)
        (MOCK_HN_STORY_41003, min(200 / 500, 1.0)),  # 0.4
        (MOCK_HN_STORY_NO_AUTHOR, min(50 / 500, 1.0)),  # 0.1
        (MOCK_HN_STORY_HIGH_SCORE, min(1000 / 500, 1.0)),  # 1.0 (capped)
    ]

    for idx, (story_data, expected_credibility) in enumerate(test_cases):
        adapter = HackerNewsAdapter()
        story_id = story_data["id"]

        async def mock_fetch_with_retry(url, client, adapter_name):
            if "topstories.json" in url:
                return MagicMock(json=lambda: [story_id])
            return MagicMock(json=lambda: story_data)

        with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
            signals = await adapter.fetch(limit=10)

        assert len(signals) == 1
        assert signals[0].credibility == expected_credibility


@pytest.mark.asyncio
async def test_hackernews_adapter_credibility_missing_score() -> None:
    """Adapter defaults to 0 credibility when score is missing."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41007])
        return MagicMock(json=lambda: MOCK_HN_STORY_MISSING_FIELDS)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert signals[0].credibility == 0.0


# ── Filter Keywords Tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_filter_keywords_matching() -> None:
    """Adapter filters stories based on filter_keywords."""
    adapter = HackerNewsAdapter(config={"filter_keywords": ["mcp", "claude"]})

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            # Fetch 3x limit when filtering
            return MagicMock(json=lambda: [41001, 41002, 41003])
        elif "item/41001.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41001)  # Has "MCP"
        elif "item/41002.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41002)  # No match
        elif "item/41003.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41003)  # No match

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should only include the one matching story
    assert len(signals) == 1
    assert signals[0].title == "Show HN: New MCP server for SQLite with Claude integration"


@pytest.mark.asyncio
async def test_hackernews_adapter_filter_keywords_case_insensitive() -> None:
    """Adapter performs case-insensitive keyword filtering."""
    adapter = HackerNewsAdapter(config={"filter_keywords": ["AI"]})

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41002])
        return MagicMock(json=lambda: MOCK_HN_STORY_41002)  # Has "AI" in title

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_hackernews_adapter_filter_keywords_fetch_multiplier() -> None:
    """Adapter fetches 3x limit when filter_keywords configured."""
    adapter = HackerNewsAdapter(config={"filter_keywords": ["test"]})

    fetch_urls = []

    async def mock_fetch_with_retry(url, client, adapter_name):
        fetch_urls.append(url)
        if "topstories.json" in url:
            return MagicMock(json=lambda: list(range(1, 100)))
        return MagicMock(json=lambda: MOCK_HN_STORY_41001)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        await adapter.fetch(limit=5)

    # First call should be topstories
    assert "topstories.json" in fetch_urls[0]

    # Should fetch up to 15 stories (5 * 3) instead of just 5
    # (but respects the limit in the end)


# ── Error Handling Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_top_stories_parse_error() -> None:
    """Adapter raises SourceParseError when top stories JSON is malformed."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        return mock_resp

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(SourceParseError) as exc_info:
            await adapter.fetch(limit=10)

    assert "failed to parse top stories JSON" in str(exc_info.value)
    assert exc_info.value.adapter_name == "hackernews"


@pytest.mark.asyncio
async def test_hackernews_adapter_top_stories_key_error() -> None:
    """Adapter raises SourceParseError when top stories response has unexpected structure."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = KeyError("unexpected key")
        return mock_resp

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(SourceParseError) as exc_info:
            await adapter.fetch(limit=10)

    assert "failed to parse top stories JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_hackernews_adapter_top_stories_type_error() -> None:
    """Adapter raises SourceParseError when top stories response has wrong type."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = TypeError("wrong type")
        return mock_resp

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(SourceParseError) as exc_info:
            await adapter.fetch(limit=10)

    assert "failed to parse top stories JSON" in str(exc_info.value)


@pytest.mark.asyncio
async def test_hackernews_adapter_item_fetch_error_continues() -> None:
    """Adapter continues fetching when individual item request fails."""
    adapter = HackerNewsAdapter()

    call_count = 0

    async def mock_fetch_with_retry(url, client, adapter_name):
        nonlocal call_count

        if "topstories.json" in url:
            return MagicMock(json=lambda: [41001, 41002, 41003])

        call_count += 1

        if "item/41001.json" in url:
            raise AdapterFetchError("hackernews", 404, url)
        elif "item/41002.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41002)
        elif "item/41003.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41003)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should have 2 signals despite first item failing
    assert len(signals) == 2
    assert signals[0].metadata["hn_id"] == 41002
    assert signals[1].metadata["hn_id"] == 41003


@pytest.mark.asyncio
async def test_hackernews_adapter_item_parse_error_continues() -> None:
    """Adapter logs warning and continues when individual item JSON is malformed."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41001, 41002])

        if "item/41001.json" in url:
            mock_resp = MagicMock()
            mock_resp.json.side_effect = ValueError("Bad JSON")
            return mock_resp
        elif "item/41002.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41002)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should have 1 signal, skipping the one with bad JSON
    assert len(signals) == 1
    assert signals[0].metadata["hn_id"] == 41002


@pytest.mark.asyncio
async def test_hackernews_adapter_http_404_error() -> None:
    """Adapter handles HTTP 404 errors from fetch_with_retry."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise AdapterFetchError("hackernews", 404, url)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.status_code == 404
    assert exc_info.value.adapter_name == "hackernews"


@pytest.mark.asyncio
async def test_hackernews_adapter_http_500_error() -> None:
    """Adapter handles HTTP 500 errors from fetch_with_retry."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise AdapterFetchError("hackernews", 500, url)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_hackernews_adapter_http_503_error() -> None:
    """Adapter handles HTTP 503 errors from fetch_with_retry."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise AdapterFetchError("hackernews", 503, url)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(AdapterFetchError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_hackernews_adapter_rate_limit_error() -> None:
    """Adapter handles HTTP 429 rate limit errors from fetch_with_retry."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise AdapterRateLimitError("hackernews", url)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(AdapterRateLimitError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.status_code == 429
    assert exc_info.value.adapter_name == "hackernews"


@pytest.mark.asyncio
async def test_hackernews_adapter_circuit_open_error() -> None:
    """Adapter handles circuit breaker open errors from fetch_with_retry."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise AdapterCircuitOpenError("hackernews", retry_after=300.0)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(AdapterCircuitOpenError) as exc_info:
            await adapter.fetch(limit=10)

    assert exc_info.value.adapter_name == "hackernews"
    assert exc_info.value.retry_after == 300.0


@pytest.mark.asyncio
async def test_hackernews_adapter_network_timeout() -> None:
    """Adapter handles network timeout errors from httpx."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise httpx.TimeoutException("Request timeout")

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(httpx.TimeoutException):
            await adapter.fetch(limit=10)


@pytest.mark.asyncio
async def test_hackernews_adapter_network_error() -> None:
    """Adapter handles network connection errors from httpx."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            raise httpx.ConnectError("Connection failed")

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        with pytest.raises(httpx.ConnectError):
            await adapter.fetch(limit=10)


# ── Empty Results Tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_empty_top_stories() -> None:
    """Adapter handles empty top stories list gracefully."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        return MagicMock(json=lambda: [])

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    assert len(signals) == 0


# ── Limit Handling Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_respects_limit() -> None:
    """Adapter stops fetching when limit is reached."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: list(range(1, 100)))
        # Return a valid story for any item request
        return MagicMock(json=lambda: MOCK_HN_STORY_41001)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=5)

    assert len(signals) == 5


@pytest.mark.asyncio
async def test_hackernews_adapter_limit_slicing() -> None:
    """Adapter slices results to exact limit at end."""
    adapter = HackerNewsAdapter()

    async def mock_fetch_with_retry(url, client, adapter_name):
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41001, 41002, 41003])
        elif "item/41001.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41001)
        elif "item/41002.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41002)
        elif "item/41003.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41003)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=2)

    assert len(signals) == 2


# ── Tag Extraction Tests ─────────────────────────────────────────────


def test_extract_tags_ai() -> None:
    """Tag extraction identifies AI-related keywords."""
    assert "ai" in _extract_tags("Building AI agents with LLM models")
    assert "ai" in _extract_tags("GPT-4 and Claude in production")
    assert "ai" in _extract_tags("Machine learning best practices")


def test_extract_tags_mcp() -> None:
    """Tag extraction identifies MCP-related keywords."""
    assert "mcp" in _extract_tags("New MCP server for SQLite")
    assert "mcp" in _extract_tags("Model Context Protocol implementation")


def test_extract_tags_agent() -> None:
    """Tag extraction identifies agent-related keywords."""
    assert "agent" in _extract_tags("Building autonomous agents")
    assert "agent" in _extract_tags("Agentic workflows with LangChain")


def test_extract_tags_rust() -> None:
    """Tag extraction identifies Rust-related keywords."""
    assert "rust" in _extract_tags("Rust compiler optimization")


def test_extract_tags_python() -> None:
    """Tag extraction identifies Python-related keywords."""
    assert "python" in _extract_tags("Python async programming guide")


def test_extract_tags_typescript() -> None:
    """Tag extraction identifies TypeScript/Node-related keywords."""
    assert "typescript" in _extract_tags("TypeScript 5.0 released")
    assert "typescript" in _extract_tags("Building APIs with Node.js")
    assert "typescript" in _extract_tags("Deno 2.0 announcement")
    assert "typescript" in _extract_tags("Bun: fast JavaScript runtime")


def test_extract_tags_security() -> None:
    """Tag extraction identifies security-related keywords."""
    assert "security" in _extract_tags("Critical security vulnerability found")
    assert "security" in _extract_tags("CVE-2024-1234 disclosure")


def test_extract_tags_devtools() -> None:
    """Tag extraction identifies devtools-related keywords."""
    assert "devtools" in _extract_tags("New developer tools for debugging")
    assert "devtools" in _extract_tags("VSCode extension for Rust")
    assert "devtools" in _extract_tags("Best IDE for Python development")


def test_extract_tags_open_source() -> None:
    """Tag extraction identifies open source-related keywords."""
    assert "open_source" in _extract_tags("Open source project reaches 10k stars")
    assert "open_source" in _extract_tags("OSS licensing guide")
    assert "open_source" in _extract_tags("New GitHub features for maintainers")


def test_extract_tags_startup() -> None:
    """Tag extraction identifies startup-related keywords."""
    assert "startup" in _extract_tags("YC-backed startup launches new product")
    assert "startup" in _extract_tags("Series A funding round")
    assert "startup" in _extract_tags("Startup raised $10M")


def test_extract_tags_multiple() -> None:
    """Tag extraction identifies multiple tags in single title."""
    tags = _extract_tags("Show HN: Open source AI agent framework in Rust")
    assert "ai" in tags
    assert "agent" in tags
    assert "rust" in tags
    assert "open_source" in tags


def test_extract_tags_case_insensitive() -> None:
    """Tag extraction is case insensitive."""
    assert "ai" in _extract_tags("Building AI Agents")
    assert "python" in _extract_tags("PYTHON Performance Optimization")


def test_extract_tags_no_matches() -> None:
    """Tag extraction returns empty list when no keywords match."""
    tags = _extract_tags("Random blog post about cats")
    assert tags == []


# ── HTTP Client Integration Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_uses_async_client() -> None:
    """Adapter uses httpx.AsyncClient with correct timeout."""
    adapter = HackerNewsAdapter()

    client_created = False
    client_timeout = None

    class MockAsyncClient:
        def __init__(self, timeout=None):
            nonlocal client_created, client_timeout
            client_created = True
            client_timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("max.sources.hackernews.httpx.AsyncClient", MockAsyncClient):
        with patch("max.sources.hackernews.fetch_with_retry") as mock_fetch:
            mock_fetch.return_value = MagicMock(json=lambda: [])

            await adapter.fetch(limit=10)

    assert client_created
    assert client_timeout == 30


# ── Integration with fetch_with_retry Tests ──────────────────────────


@pytest.mark.asyncio
async def test_hackernews_adapter_calls_fetch_with_retry_correctly() -> None:
    """Adapter calls fetch_with_retry with correct parameters."""
    adapter = HackerNewsAdapter()

    call_args_list = []

    async def mock_fetch_with_retry(url, client, adapter_name):
        call_args_list.append({
            "url": url,
            "adapter_name": adapter_name,
        })
        if "topstories.json" in url:
            return MagicMock(json=lambda: [])
        return MagicMock(json=lambda: MOCK_HN_STORY_41001)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        await adapter.fetch(limit=10)

    assert len(call_args_list) >= 1
    first_call = call_args_list[0]
    assert first_call["url"] == "https://hacker-news.firebaseio.com/v0/topstories.json"
    assert first_call["adapter_name"] == "hackernews"


@pytest.mark.asyncio
async def test_hackernews_adapter_fetch_with_retry_per_item() -> None:
    """Adapter calls fetch_with_retry for each story item."""
    adapter = HackerNewsAdapter()

    call_urls = []

    async def mock_fetch_with_retry(url, client, adapter_name):
        call_urls.append(url)
        if "topstories.json" in url:
            return MagicMock(json=lambda: [41001, 41002])
        elif "item/41001.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41001)
        elif "item/41002.json" in url:
            return MagicMock(json=lambda: MOCK_HN_STORY_41002)

    with patch("max.sources.hackernews.fetch_with_retry", mock_fetch_with_retry):
        signals = await adapter.fetch(limit=10)

    # Should have 3 calls: 1 for topstories, 2 for items
    assert len(call_urls) == 3
    assert "topstories.json" in call_urls[0]
    assert "item/41001.json" in call_urls[1]
    assert "item/41002.json" in call_urls[2]


# ── Base Adapter Interface Tests ─────────────────────────────────────


def test_hackernews_adapter_inherits_from_source_adapter() -> None:
    """Adapter properly inherits from SourceAdapter base class."""
    from max.sources.base import SourceAdapter

    adapter = HackerNewsAdapter()
    assert isinstance(adapter, SourceAdapter)


def test_hackernews_adapter_implements_required_properties() -> None:
    """Adapter implements all required abstract properties."""
    adapter = HackerNewsAdapter()

    # These should not raise AttributeError
    assert hasattr(adapter, "name")
    assert hasattr(adapter, "source_type")
    assert hasattr(adapter, "fetch")

    # Verify they're callable/accessible
    assert callable(adapter.fetch)
    _ = adapter.name
    _ = adapter.source_type


def test_hackernews_adapter_accepts_config() -> None:
    """Adapter accepts and stores config dict."""
    config = {"filter_keywords": ["test"], "custom_field": "value"}
    adapter = HackerNewsAdapter(config=config)

    assert adapter._config == config
    assert adapter.filter_keywords == ["test"]


def test_hackernews_adapter_no_config() -> None:
    """Adapter works without config."""
    adapter = HackerNewsAdapter()
    assert adapter._config == {}
