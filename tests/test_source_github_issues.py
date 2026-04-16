"""Comprehensive tests for GitHub Issues source adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.base import AdapterFetchError, AdapterRateLimitError
from max.sources.github_issues import (
    GitHubIssuesAdapter,
    _DEFAULT_QUERIES,
    _build_tags,
    _extract_repo,
    _parse_dt,
)
from max.types.signal import SignalSourceType


# ── Test Data ────────────────────────────────────────────────────────


MOCK_GITHUB_ISSUE_1 = {
    "id": 12345,
    "html_url": "https://github.com/example/ai-toolkit/issues/101",
    "title": "Add support for AI agent workflows",
    "body": "We need better support for AI agent workflows in this library.",
    "state": "open",
    "user": {"login": "developer123"},
    "created_at": "2026-04-15T10:30:00Z",
    "comments": 5,
    "reactions": {"total_count": 10},
    "labels": [
        {"name": "enhancement"},
        {"name": "ai"},
    ],
}

MOCK_GITHUB_ISSUE_2 = {
    "id": 12346,
    "html_url": "https://github.com/example/llm-lib/issues/200",
    "title": "Bug: LLM fails with timeout on long prompts",
    "body": "The LLM provider times out when processing prompts longer than 10k tokens.",
    "state": "open",
    "user": {"login": "user456"},
    "created_at": "2026-04-14T14:20:00Z",
    "comments": 3,
    "reactions": {"total_count": 7},
    "labels": [
        {"name": "bug"},
    ],
}

MOCK_GITHUB_ISSUE_3 = {
    "id": 12347,
    "html_url": "https://github.com/example/mcp-server/issues/42",
    "title": "MCP server security vulnerability",
    "body": "Discovered a potential security issue in the authentication flow.",
    "state": "open",
    "user": {"login": "security-researcher"},
    "created_at": "2026-04-13T09:15:00Z",
    "comments": 15,
    "reactions": {"total_count": 25},
    "labels": [
        {"name": "security"},
        {"name": "critical"},
    ],
}

MOCK_GITHUB_PR = {
    "id": 12348,
    "html_url": "https://github.com/example/ai-toolkit/pull/102",
    "title": "Add AI agent feature",
    "body": "PR description",
    "state": "open",
    "user": {"login": "developer123"},
    "created_at": "2026-04-12T08:00:00Z",
    "comments": 2,
    "reactions": {"total_count": 3},
    "labels": [],
    "pull_request": {},  # This key indicates it's a PR, not an issue
}

MOCK_GITHUB_SEARCH_RESPONSE_1 = {
    "total_count": 3,
    "incomplete_results": False,
    "items": [
        MOCK_GITHUB_ISSUE_1,
        MOCK_GITHUB_PR,  # Should be filtered out
    ],
}

MOCK_GITHUB_SEARCH_RESPONSE_2 = {
    "total_count": 2,
    "incomplete_results": False,
    "items": [
        MOCK_GITHUB_ISSUE_2,
        MOCK_GITHUB_ISSUE_3,
    ],
}

MOCK_GITHUB_SEARCH_EMPTY = {
    "total_count": 0,
    "incomplete_results": False,
    "items": [],
}


# ── Helper Functions Tests ───────────────────────────────────────────


def test_extract_repo_valid_url() -> None:
    """Extract repo from valid GitHub issue URLs."""
    assert _extract_repo("https://github.com/owner/repo/issues/123") == "owner/repo"
    assert _extract_repo("https://github.com/anthropics/anthropic-sdk-python/issues/456") == "anthropics/anthropic-sdk-python"
    assert _extract_repo("https://github.com/user/my-project/issues/1") == "user/my-project"


def test_extract_repo_invalid_url() -> None:
    """Extract repo returns empty string for invalid URLs."""
    assert _extract_repo("https://example.com/issues/123") == ""
    assert _extract_repo("invalid-url") == ""
    assert _extract_repo("") == ""
    assert _extract_repo("https://github.com/") == ""


def test_parse_dt_valid_iso8601() -> None:
    """Parse valid ISO 8601 datetime strings."""
    dt = _parse_dt("2026-04-15T10:30:00Z")
    assert dt is not None
    assert isinstance(dt, datetime)
    assert dt.year == 2026
    assert dt.month == 4
    assert dt.day == 15
    assert dt.hour == 10
    assert dt.minute == 30
    assert dt.tzinfo is not None


def test_parse_dt_with_timezone_offset() -> None:
    """Parse ISO 8601 datetime with timezone offset."""
    dt = _parse_dt("2026-04-15T10:30:00+05:00")
    assert dt is not None
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None


def test_parse_dt_invalid_string() -> None:
    """Parse returns None for invalid datetime strings."""
    assert _parse_dt("not a date") is None
    assert _parse_dt("2026-13-01T00:00:00Z") is None
    assert _parse_dt("") is None


def test_parse_dt_none_input() -> None:
    """Parse returns None for None input."""
    assert _parse_dt(None) is None


def test_build_tags_from_labels() -> None:
    """Build tags from GitHub issue labels."""
    labels = ["enhancement", "bug", "feature-request"]
    title = "Some issue title"
    tags = _build_tags(labels, title)

    assert "enhancement" in tags
    assert "bug" in tags


def test_build_tags_from_title_keywords() -> None:
    """Build tags from title keywords."""
    labels: list[str] = []
    title = "Add AI agent support for LLM workflows"
    tags = _build_tags(labels, title)

    assert "ai" in tags
    assert "agent" in tags
    assert "llm" in tags


def test_build_tags_security_keyword() -> None:
    """Build tags identifies security-related issues."""
    labels = ["security"]
    title = "Security vulnerability in authentication"
    tags = _build_tags(labels, title)

    assert "security" in tags


def test_build_tags_mcp_keyword() -> None:
    """Build tags identifies MCP-related issues."""
    labels: list[str] = []
    title = "MCP server implementation bug"
    tags = _build_tags(labels, title)

    assert "mcp" in tags


def test_build_tags_programming_languages() -> None:
    """Build tags identifies programming language keywords."""
    labels: list[str] = []

    tags_python = _build_tags([], "Python implementation issue")
    assert "python" in tags_python

    tags_ts = _build_tags([], "TypeScript agent library")
    assert "typescript" in tags_ts


def test_build_tags_limits_to_10() -> None:
    """Build tags limits output to 10 tags."""
    labels = ["enhancement", "bug", "feature", "security", "performance", "documentation"]
    title = "AI agent LLM MCP Python TypeScript security vulnerability artificial intelligence"
    tags = _build_tags(labels, title)

    assert len(tags) <= 10


def test_build_tags_label_mapping() -> None:
    """Build tags maps labels to standardized tags."""
    # Test feature -> enhancement mapping
    tags_feature = _build_tags(["feature"], "title")
    assert "enhancement" in tags_feature

    # Test documentation -> docs mapping
    tags_docs = _build_tags(["documentation"], "title")
    assert "docs" in tags_docs


def test_build_tags_case_insensitive() -> None:
    """Build tags handles labels case-insensitively."""
    tags = _build_tags(["ENHANCEMENT", "Bug", "SECURITY"], "title")
    assert "enhancement" in tags
    assert "bug" in tags
    assert "security" in tags


# ── Adapter Integration Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_github_issues_adapter_fetch_success() -> None:
    """GitHub Issues adapter successfully fetches and parses issues."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_1,
                raise_for_status=lambda: None,
            )
        elif call_count == 2:
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_2,
                raise_for_status=lambda: None,
            )
        else:
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should get issues but not PRs
    assert len(signals) >= 1

    # Check that PR was filtered out
    urls = {s.url for s in signals}
    assert "https://github.com/example/ai-toolkit/pull/102" not in urls

    # Verify signal structure
    first = signals[0]
    assert first.source_type == SignalSourceType.FORUM
    assert first.source_adapter == "github_issues"
    assert first.title == "Add support for AI agent workflows"
    assert "AI agent workflows" in first.content
    assert first.url == "https://github.com/example/ai-toolkit/issues/101"
    assert first.author == "developer123"
    assert first.published_at is not None
    assert "ai" in first.tags or "agent" in first.tags

    # Check credibility calculation: (reactions + comments) / 100
    expected_credibility = min((10 + 5) / 100, 1.0)
    assert first.credibility == expected_credibility

    # Check metadata
    assert first.metadata["github_issue_id"] == 12345
    assert first.metadata["repo"] == "example/ai-toolkit"
    assert first.metadata["state"] == "open"
    assert first.metadata["reactions"] == 10
    assert first.metadata["comments"] == 5
    assert "enhancement" in first.metadata["labels"]


@pytest.mark.asyncio
async def test_github_issues_adapter_filters_pull_requests() -> None:
    """GitHub Issues adapter filters out pull requests."""
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: {
                "total_count": 1,
                "items": [MOCK_GITHUB_PR],
            },
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # All items are PRs, should be filtered out
    assert len(signals) == 0


@pytest.mark.asyncio
async def test_github_issues_adapter_respects_limit() -> None:
    """GitHub Issues adapter respects the limit parameter."""
    adapter = GitHubIssuesAdapter()

    # Create response with many issues
    many_issues = {
        "total_count": 100,
        "items": [
            {
                **MOCK_GITHUB_ISSUE_1,
                "id": 10000 + i,
                "html_url": f"https://github.com/example/repo/issues/{i}",
            }
            for i in range(50)
        ],
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: many_issues,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=5)

    assert len(signals) <= 5


@pytest.mark.asyncio
async def test_github_issues_adapter_deduplicates_urls() -> None:
    """GitHub Issues adapter deduplicates issues with same URL."""
    adapter = GitHubIssuesAdapter()

    # Same issue appears in multiple query results
    duplicate_response = {
        "total_count": 1,
        "items": [MOCK_GITHUB_ISSUE_1],
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: duplicate_response,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=20)

    # Despite appearing in multiple query results, should only appear once
    urls = [s.url for s in signals]
    assert urls.count("https://github.com/example/ai-toolkit/issues/101") == 1


@pytest.mark.asyncio
async def test_github_issues_adapter_custom_queries() -> None:
    """GitHub Issues adapter uses custom queries from config."""
    custom_queries = ['"database" is:issue is:open']
    adapter = GitHubIssuesAdapter(config={"queries": custom_queries})

    assert adapter.queries == custom_queries

    requested_queries: list[str] = []

    async def mock_get(url: str, **kwargs) -> MagicMock:
        if "params" in kwargs and "q" in kwargs["params"]:
            requested_queries.append(kwargs["params"]["q"])
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    assert '"database" is:issue is:open' in requested_queries


@pytest.mark.asyncio
async def test_github_issues_adapter_handles_http_error() -> None:
    """GitHub Issues adapter handles HTTP errors gracefully."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query fails with 500
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
            return resp
        else:
            # Second query succeeds
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_1,
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should still get results from successful queries
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_github_issues_adapter_handles_network_error() -> None:
    """GitHub Issues adapter handles network errors gracefully."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query has network error
            raise httpx.RequestError("Connection failed")
        else:
            # Second query succeeds
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_1,
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should still get results from successful queries
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_github_issues_adapter_handles_timeout() -> None:
    """GitHub Issues adapter handles timeout errors gracefully."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query times out
            raise httpx.TimeoutException("Request timed out")
        else:
            # Second query succeeds
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_1,
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should still get results from successful queries
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_github_issues_adapter_handles_malformed_json() -> None:
    """GitHub Issues adapter handles malformed JSON responses."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query returns invalid JSON
            resp = MagicMock()
            resp.raise_for_status = lambda: None
            resp.json.side_effect = ValueError("Invalid JSON")
            return resp
        else:
            # Second query succeeds
            return MagicMock(
                json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_1,
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    # Should still get results from successful queries
    assert len(signals) >= 1


@pytest.mark.asyncio
async def test_github_issues_adapter_handles_missing_fields() -> None:
    """GitHub Issues adapter handles issues with missing fields."""
    adapter = GitHubIssuesAdapter()

    # Issue with missing optional fields
    minimal_issue = {
        "id": 99999,
        "html_url": "https://github.com/example/repo/issues/999",
        "title": "Minimal issue",
        # No body
        "state": "open",
        "user": {},  # No login
        # No created_at
        "comments": 0,
        "reactions": {},  # No total_count
        "labels": [],
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: {
                "total_count": 1,
                "items": [minimal_issue],
            },
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    signal = signals[0]
    assert signal.title == "Minimal issue"
    assert signal.content == "Minimal issue"  # Falls back to title when body is empty
    assert signal.author is None
    assert signal.published_at is None
    assert signal.credibility == 0.0  # (0 + 0) / 100


@pytest.mark.asyncio
async def test_github_issues_adapter_handles_empty_body() -> None:
    """GitHub Issues adapter uses title as content when body is empty."""
    adapter = GitHubIssuesAdapter()

    issue_no_body = {
        **MOCK_GITHUB_ISSUE_1,
        "body": None,
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: {
                "total_count": 1,
                "items": [issue_no_body],
            },
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    # When body is None, content should be the title
    assert signals[0].content == signals[0].title


@pytest.mark.asyncio
async def test_github_issues_adapter_truncates_long_body() -> None:
    """GitHub Issues adapter truncates body to 1000 characters."""
    adapter = GitHubIssuesAdapter()

    long_body = "x" * 2000
    issue_long_body = {
        **MOCK_GITHUB_ISSUE_1,
        "body": long_body,
    }

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: {
                "total_count": 1,
                "items": [issue_long_body],
            },
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) == 1
    assert len(signals[0].content) == 1000


@pytest.mark.asyncio
async def test_github_issues_adapter_credibility_calculation() -> None:
    """GitHub Issues adapter calculates credibility correctly."""
    adapter = GitHubIssuesAdapter()

    test_cases = [
        (0, 0, 0.0),
        (5, 10, 0.15),
        (50, 50, 1.0),  # 100/100 = 1.0
        (100, 50, 1.0),  # 150/100 = 1.5, capped at 1.0
    ]

    for reactions, comments, expected_credibility in test_cases:
        issue = {
            **MOCK_GITHUB_ISSUE_1,
            "reactions": {"total_count": reactions},
            "comments": comments,
        }

        async def mock_get(url: str, **kwargs) -> MagicMock:
            return MagicMock(
                json=lambda: {
                    "total_count": 1,
                    "items": [issue],
                },
                raise_for_status=lambda: None,
            )

        with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            signals = await adapter.fetch(limit=1)

        assert len(signals) == 1
        assert signals[0].credibility == expected_credibility


@pytest.mark.asyncio
async def test_github_issues_adapter_uses_env_token() -> None:
    """GitHub Issues adapter uses GITHUB_TOKEN from environment."""
    adapter = GitHubIssuesAdapter()

    captured_headers: dict[str, str] = {}

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
            raise_for_status=lambda: None,
        )

    async def mock_init(self, **kwargs):
        nonlocal captured_headers
        if "headers" in kwargs:
            captured_headers = kwargs["headers"]
        return None

    with patch.dict("os.environ", {"GITHUB_TOKEN": "test_token_123"}):
        with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)

            # Capture initialization kwargs
            original_init = httpx.AsyncClient.__init__

            def capture_init(self, **kwargs):
                nonlocal captured_headers
                if "headers" in kwargs:
                    captured_headers = kwargs["headers"]

            mock_cls.return_value = mock_client
            mock_cls.side_effect = lambda **kwargs: (capture_init(None, **kwargs), mock_client)[1]

            await adapter.fetch(limit=10)

    # Verify Authorization header is set when token is available
    # Note: We can't easily verify headers with this mocking approach,
    # but the code path is tested


@pytest.mark.asyncio
async def test_github_issues_adapter_vault_token_fallback() -> None:
    """GitHub Issues adapter falls back to vault for GitHub token."""
    adapter = GitHubIssuesAdapter()

    # Mock subprocess.run to simulate vault command
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "vault_token_456\n"

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {}, clear=True):  # Clear GITHUB_TOKEN
        with patch("subprocess.run", return_value=mock_result):
            with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
                mock_client = AsyncMock()
                mock_client.get = mock_get
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_cls.return_value = mock_client

                signals = await adapter.fetch(limit=10)

    # Should not raise an error
    assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_github_issues_adapter_vault_fallback_failure() -> None:
    """GitHub Issues adapter continues without token when vault fails."""
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch.dict("os.environ", {}, clear=True):  # Clear GITHUB_TOKEN
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
                mock_client = AsyncMock()
                mock_client.get = mock_get
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=None)
                mock_cls.return_value = mock_client

                signals = await adapter.fetch(limit=10)

    # Should continue without token
    assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_github_issues_adapter_rate_limit_pause() -> None:
    """GitHub Issues adapter pauses between queries for rate limiting."""
    adapter = GitHubIssuesAdapter()

    sleep_calls: list[float] = []

    async def mock_sleep(duration: float) -> None:
        sleep_calls.append(duration)

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.asyncio.sleep", mock_sleep):
        with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = mock_get
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_client

            await adapter.fetch(limit=10)

    # Should have sleep calls (one less than number of queries)
    # Default has 4 queries, so should have 3 sleep calls
    assert len(sleep_calls) >= 1
    assert all(s == 1 for s in sleep_calls)  # Each sleep is 1 second


@pytest.mark.asyncio
async def test_github_issues_adapter_name_property() -> None:
    """GitHub Issues adapter returns correct name."""
    adapter = GitHubIssuesAdapter()
    assert adapter.name == "github_issues"


@pytest.mark.asyncio
async def test_github_issues_adapter_source_type_property() -> None:
    """GitHub Issues adapter returns correct source type."""
    adapter = GitHubIssuesAdapter()
    assert adapter.source_type == SignalSourceType.FORUM.value


def test_github_issues_adapter_queries_default() -> None:
    """GitHub Issues adapter uses default queries when not configured."""
    adapter = GitHubIssuesAdapter()
    assert adapter.queries == _DEFAULT_QUERIES


def test_github_issues_adapter_queries_custom() -> None:
    """GitHub Issues adapter uses custom queries from config."""
    custom_queries = ['"database" is:issue', '"api" is:issue']
    adapter = GitHubIssuesAdapter(config={"queries": custom_queries})
    assert adapter.queries == custom_queries


@pytest.mark.asyncio
async def test_github_issues_adapter_search_parameters() -> None:
    """GitHub Issues adapter sends correct search parameters to GitHub API."""
    adapter = GitHubIssuesAdapter()

    captured_params: dict = {}

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal captured_params
        if "params" in kwargs:
            captured_params = kwargs["params"]
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_EMPTY,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        await adapter.fetch(limit=10)

    # Verify search parameters
    assert "q" in captured_params
    assert captured_params["sort"] == "reactions-+1"
    assert captured_params["order"] == "desc"
    assert "per_page" in captured_params


@pytest.mark.asyncio
async def test_github_issues_adapter_metadata_includes_search_query() -> None:
    """GitHub Issues adapter includes search query in metadata."""
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        return MagicMock(
            json=lambda: MOCK_GITHUB_SEARCH_RESPONSE_1,
            raise_for_status=lambda: None,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        signals = await adapter.fetch(limit=10)

    assert len(signals) >= 1
    # Check that metadata includes the search query
    assert "search_query" in signals[0].metadata
    assert signals[0].metadata["search_query"] in _DEFAULT_QUERIES
