"""Tests for GitHub import adapter — repository signal collection."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.imports.github_adapter import (
    GitHubAdapter,
    _build_tags,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────

MOCK_REPO = {
    "full_name": "anthropics/claude-code",
    "description": "CLI tool for AI-assisted coding",
    "html_url": "https://github.com/anthropics/claude-code",
    "stargazers_count": 12000,
    "forks_count": 800,
    "open_issues_count": 42,
    "language": "TypeScript",
    "topics": ["ai-agent", "cli", "developer-tools"],
    "created_at": "2024-11-01T10:00:00Z",
    "updated_at": "2026-05-09T08:00:00Z",
    "owner": {"login": "anthropics"},
    "license": {"spdx_id": "MIT"},
    "watchers_count": 12000,
}

MOCK_REPO_2 = {
    "full_name": "modelcontextprotocol/servers",
    "description": "MCP server implementations",
    "html_url": "https://github.com/modelcontextprotocol/servers",
    "stargazers_count": 5000,
    "forks_count": 300,
    "open_issues_count": 15,
    "language": "Python",
    "topics": ["mcp", "model-context-protocol", "llm"],
    "created_at": "2024-06-15T12:00:00Z",
    "updated_at": "2026-05-08T14:00:00Z",
    "owner": {"login": "modelcontextprotocol"},
    "license": {"spdx_id": "Apache-2.0"},
    "watchers_count": 5000,
}

MOCK_SEARCH_RESPONSE = {
    "total_count": 2,
    "incomplete_results": False,
    "items": [MOCK_REPO, MOCK_REPO_2],
}

MOCK_EMPTY_RESPONSE = {
    "total_count": 0,
    "incomplete_results": False,
    "items": [],
}


def _mock_response(payload: dict, *, status_code: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = payload
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


# ── Unit tests ───────────────────────────────────────────────────────


def test_parse_dt_valid() -> None:
    dt = _parse_dt("2026-05-09T08:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.tzinfo is not None


def test_parse_dt_none() -> None:
    assert _parse_dt(None) is None


def test_parse_dt_invalid() -> None:
    assert _parse_dt("not-a-date") is None


def test_build_tags_basic() -> None:
    tags = _build_tags(["ai-agent", "cli"], "TypeScript", "mcp")
    assert "agent" in tags
    assert "devtools" in tags
    assert "typescript" in tags
    assert "mcp" in tags


def test_build_tags_language_mapping() -> None:
    tags = _build_tags([], "Python", "llm")
    assert "python" in tags
    assert "ai" in tags  # llm topic maps to ai


def test_build_tags_empty() -> None:
    tags = _build_tags([], None, "custom-topic")
    assert "custom-topic" in tags
    assert isinstance(tags, list)


# ── Adapter property tests ───────────────────────────────────────────


def test_adapter_name() -> None:
    adapter = GitHubAdapter()
    assert adapter.name == "github_import"


def test_adapter_source_type() -> None:
    adapter = GitHubAdapter()
    assert adapter.source_type == SignalSourceType.TRENDING.value


def test_adapter_default_topics() -> None:
    adapter = GitHubAdapter()
    assert "mcp" in adapter.topics
    assert "llm" in adapter.topics


def test_adapter_custom_topics() -> None:
    adapter = GitHubAdapter(config={"topics": ["react", "vue"]})
    assert adapter.topics == ["react", "vue"]


def test_adapter_language_config() -> None:
    adapter = GitHubAdapter(config={"language": "Rust"})
    assert adapter.language == "Rust"


def test_adapter_language_default_none() -> None:
    adapter = GitHubAdapter()
    assert adapter.language is None


def test_adapter_query_config() -> None:
    adapter = GitHubAdapter(config={"query": "stars:>1000"})
    assert adapter.query == "stars:>1000"


# ── Fetch tests with mocked API ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_parses_repositories() -> None:
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 2

    sig = signals[0]
    assert sig.title == "anthropics/claude-code"
    assert sig.source_adapter == "github_import"
    assert sig.source_type == SignalSourceType.TRENDING
    assert sig.url == "https://github.com/anthropics/claude-code"
    assert sig.author == "anthropics"
    assert sig.metadata["stars"] == 12000
    assert sig.metadata["forks"] == 800
    assert sig.metadata["open_issues"] == 42
    assert sig.metadata["language"] == "TypeScript"
    assert sig.metadata["license"] == "MIT"
    assert sig.published_at is not None


@pytest.mark.asyncio
async def test_fetch_respects_limit() -> None:
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)

        signals = await adapter.fetch(limit=1)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_deduplicates_repos() -> None:
    dup_response = {
        "total_count": 2,
        "items": [MOCK_REPO, MOCK_REPO],  # same repo twice
    }
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(dup_response)

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1


@pytest.mark.asyncio
async def test_fetch_handles_api_error() -> None:
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.side_effect = Exception("API error")

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_empty_response() -> None:
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)

        signals = await adapter.fetch(limit=10)

    assert signals == []


@pytest.mark.asyncio
async def test_fetch_with_language_filter() -> None:
    adapter = GitHubAdapter(config={"topics": ["mcp"], "language": "Python"})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)

        await adapter.fetch(limit=10)

    call_args = mock_fetch.call_args
    query = call_args.kwargs.get("params", {}).get("q", "")
    assert "language:Python" in query


@pytest.mark.asyncio
async def test_fetch_with_custom_query() -> None:
    adapter = GitHubAdapter(config={"query": "stars:>1000 language:Rust"})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_SEARCH_RESPONSE)

        await adapter.fetch(limit=10)

    call_args = mock_fetch.call_args
    query = call_args.kwargs.get("params", {}).get("q", "")
    assert "stars:>1000" in query


@pytest.mark.asyncio
async def test_fetch_credibility_capped_at_one() -> None:
    huge_stars_repo = {**MOCK_REPO, "stargazers_count": 100000}
    response = {"total_count": 1, "items": [huge_stars_repo]}
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(response)

        signals = await adapter.fetch(limit=10)

    assert signals[0].credibility == 1.0


@pytest.mark.asyncio
async def test_fetch_missing_description_uses_name() -> None:
    no_desc_repo = {**MOCK_REPO, "description": None}
    response = {"total_count": 1, "items": [no_desc_repo]}
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(response)

        signals = await adapter.fetch(limit=10)

    assert signals[0].content == "anthropics/claude-code"


@pytest.mark.asyncio
@patch("max.imports.github_adapter._get_token", return_value="ghp_test123")
async def test_fetch_uses_auth_token(mock_token: MagicMock) -> None:
    adapter = GitHubAdapter(config={"topics": ["mcp"]})

    with patch("max.imports.github_adapter.fetch_with_retry", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = _mock_response(MOCK_EMPTY_RESPONSE)

        await adapter.fetch(limit=10)

    # Verify the client was created (token is set in client headers, not in
    # fetch_with_retry params directly). We just confirm no crash with token.
    mock_fetch.assert_called()
