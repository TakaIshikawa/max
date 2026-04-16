"""Comprehensive tests for source adapter error hierarchy."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from max.sources.errors import (
    SourceAuthError,
    SourceError,
    SourceParseError,
    SourceRateLimitError,
    SourceTransientError,
)
from max.sources.github_issues import GitHubIssuesAdapter
from max.sources.pypi_registry import PyPIRegistryAdapter
from max.sources.reddit import RedditAdapter


# ── Error Construction Tests ──────────────────────────────────────────


def test_source_error_base() -> None:
    """SourceError is the base exception with adapter_name and message."""
    error = SourceError("Something went wrong", adapter_name="test_adapter")
    assert error.adapter_name == "test_adapter"
    assert error.message == "Something went wrong"
    assert str(error) == "test_adapter: Something went wrong"


def test_source_error_without_adapter_name() -> None:
    """SourceError can be created without adapter_name."""
    error = SourceError("Generic error")
    assert error.adapter_name is None
    assert str(error) == "Generic error"


def test_source_rate_limit_error() -> None:
    """SourceRateLimitError includes retry_after."""
    error = SourceRateLimitError(
        "Rate limit hit",
        adapter_name="test",
        retry_after=60.0,
    )
    assert isinstance(error, SourceError)
    assert error.adapter_name == "test"
    assert error.message == "Rate limit hit"
    assert error.retry_after == 60.0


def test_source_rate_limit_error_no_retry_after() -> None:
    """SourceRateLimitError can have None retry_after."""
    error = SourceRateLimitError("Rate limit hit", adapter_name="test")
    assert error.retry_after is None


def test_source_auth_error() -> None:
    """SourceAuthError indicates authentication failure."""
    error = SourceAuthError("Forbidden", adapter_name="test")
    assert isinstance(error, SourceError)
    assert error.adapter_name == "test"
    assert error.message == "Forbidden"


def test_source_transient_error() -> None:
    """SourceTransientError includes optional retry_after."""
    error = SourceTransientError(
        "Server unavailable",
        adapter_name="test",
        retry_after=120.0,
    )
    assert isinstance(error, SourceError)
    assert error.adapter_name == "test"
    assert error.message == "Server unavailable"
    assert error.retry_after == 120.0


def test_source_transient_error_no_retry_after() -> None:
    """SourceTransientError can have None retry_after."""
    error = SourceTransientError("Timeout", adapter_name="test")
    assert error.retry_after is None


def test_source_parse_error() -> None:
    """SourceParseError indicates malformed response data."""
    error = SourceParseError("Invalid JSON", adapter_name="test")
    assert isinstance(error, SourceError)
    assert error.adapter_name == "test"
    assert error.message == "Invalid JSON"


def test_inheritance_chain() -> None:
    """All error types inherit from SourceError."""
    assert issubclass(SourceRateLimitError, SourceError)
    assert issubclass(SourceAuthError, SourceError)
    assert issubclass(SourceTransientError, SourceError)
    assert issubclass(SourceParseError, SourceError)


# ── GitHub Issues Adapter Error Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_github_issues_raises_rate_limit_error() -> None:
    """GitHub Issues adapter raises SourceRateLimitError on HTTP 429."""
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "120"}
        raise httpx.HTTPStatusError(
            "Too Many Requests",
            request=MagicMock(),
            response=response,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceRateLimitError) as exc_info:
            await adapter.fetch(limit=10)

        error = exc_info.value
        assert error.adapter_name == "github_issues"
        assert error.retry_after == 120.0
        assert "Rate limit exceeded" in error.message


@pytest.mark.asyncio
async def test_github_issues_raises_auth_error_401() -> None:
    """GitHub Issues adapter raises SourceAuthError on HTTP 401."""
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 401
        response.headers = {}
        raise httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=response,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceAuthError) as exc_info:
            await adapter.fetch(limit=10)

        error = exc_info.value
        assert error.adapter_name == "github_issues"
        assert "Authentication failed" in error.message
        assert "401" in error.message


@pytest.mark.asyncio
async def test_github_issues_raises_auth_error_403() -> None:
    """GitHub Issues adapter raises SourceAuthError on HTTP 403."""
    adapter = GitHubIssuesAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 403
        response.headers = {}
        raise httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=response,
        )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceAuthError) as exc_info:
            await adapter.fetch(limit=10)

        error = exc_info.value
        assert error.adapter_name == "github_issues"
        assert "403" in error.message


@pytest.mark.asyncio
async def test_github_issues_continues_on_transient_error_500() -> None:
    """GitHub Issues adapter logs and continues on HTTP 500 for a query."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query fails with 500
            response = MagicMock()
            response.status_code = 500
            response.headers = {}
            raise httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=response,
            )
        else:
            # Subsequent queries succeed
            return MagicMock(
                json=lambda: {"total_count": 0, "items": []},
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        # Should not raise — continues with other queries
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_github_issues_continues_on_network_failure() -> None:
    """GitHub Issues adapter logs and continues on network errors for a query."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query has network error
            raise httpx.ConnectError("Connection refused")
        else:
            # Subsequent queries succeed
            return MagicMock(
                json=lambda: {"total_count": 0, "items": []},
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        # Should not raise — continues with other queries
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_github_issues_continues_on_parse_error() -> None:
    """GitHub Issues adapter logs and continues on malformed JSON for a query."""
    adapter = GitHubIssuesAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First query has parse error
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.json = MagicMock(side_effect=ValueError("Invalid JSON"))
            return response
        else:
            # Subsequent queries succeed
            return MagicMock(
                json=lambda: {"total_count": 0, "items": []},
                raise_for_status=lambda: None,
            )

    with patch("max.sources.github_issues.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        # Should not raise — continues with other queries
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


# ── Reddit Adapter Error Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_reddit_continues_on_parse_error() -> None:
    """Reddit adapter logs and continues on malformed JSON for a subreddit."""
    # Configure adapter with multiple subreddits
    adapter = RedditAdapter(config={"subreddits": ["test1", "test2"]})

    call_count = 0

    async def mock_fetch(url: str, client, *, adapter_name: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First subreddit has parse error
            response = MagicMock()
            response.json = MagicMock(side_effect=ValueError("Invalid JSON"))
            return response
        else:
            # Subsequent subreddits succeed
            return MagicMock(
                json=lambda: {"data": {"children": []}},
            )

    with patch("max.sources.reddit.fetch_with_retry", new=mock_fetch):
        # Should not raise — continues with other subreddits
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


# ── PyPI Registry Adapter Error Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_pypi_raises_rate_limit_error() -> None:
    """PyPI Registry adapter raises SourceRateLimitError on HTTP 429."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "60"}
        raise httpx.HTTPStatusError(
            "Too Many Requests",
            request=MagicMock(),
            response=response,
        )

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceRateLimitError) as exc_info:
            await adapter.fetch(limit=10)

        error = exc_info.value
        assert error.adapter_name == "pypi_registry"
        assert error.retry_after == 60.0
        assert "Rate limit exceeded" in error.message


@pytest.mark.asyncio
async def test_pypi_raises_auth_error() -> None:
    """PyPI Registry adapter raises SourceAuthError on HTTP 403."""
    adapter = PyPIRegistryAdapter()

    async def mock_get(url: str, **kwargs) -> MagicMock:
        response = MagicMock()
        response.status_code = 403
        response.headers = {}
        raise httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=response,
        )

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        with pytest.raises(SourceAuthError) as exc_info:
            await adapter.fetch(limit=10)

        error = exc_info.value
        assert error.adapter_name == "pypi_registry"
        assert "403" in error.message


@pytest.mark.asyncio
async def test_pypi_continues_on_transient_error() -> None:
    """PyPI Registry adapter logs and continues on HTTP 503 for a feed."""
    adapter = PyPIRegistryAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First feed fails with 503
            response = MagicMock()
            response.status_code = 503
            response.headers = {}
            raise httpx.HTTPStatusError(
                "Service Unavailable",
                request=MagicMock(),
                response=response,
            )
        else:
            # Second feed succeeds but with no matching packages
            return MagicMock(
                text='<?xml version="1.0"?><rss><channel></channel></rss>',
                raise_for_status=lambda: None,
            )

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        # Should not raise — continues with other feeds
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_pypi_continues_on_timeout() -> None:
    """PyPI Registry adapter logs and continues on timeout for a feed."""
    adapter = PyPIRegistryAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First feed times out
            raise httpx.TimeoutException("Request timed out")
        else:
            # Second feed succeeds but with no matching packages
            return MagicMock(
                text='<?xml version="1.0"?><rss><channel></channel></rss>',
                raise_for_status=lambda: None,
            )

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        # Should not raise — continues with other feeds
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


@pytest.mark.asyncio
async def test_pypi_continues_on_parse_error() -> None:
    """PyPI Registry adapter logs and continues on malformed XML for a feed."""
    adapter = PyPIRegistryAdapter()

    call_count = 0

    async def mock_get(url: str, **kwargs) -> MagicMock:
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # First feed has malformed XML
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.text = "<<<invalid xml>>>"
            return response
        else:
            # Second feed succeeds but with no matching packages
            return MagicMock(
                text='<?xml version="1.0"?><rss><channel></channel></rss>',
                raise_for_status=lambda: None,
            )

    with patch("max.sources.pypi_registry.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_client

        # Should not raise — continues with other feeds
        signals = await adapter.fetch(limit=10)
        assert isinstance(signals, list)


# ── Error Catching Tests ──────────────────────────────────────────────


def test_catch_base_source_error() -> None:
    """Callers can catch the base SourceError for all error types."""
    errors = [
        SourceRateLimitError("rate limit", adapter_name="test"),
        SourceAuthError("auth failed", adapter_name="test"),
        SourceTransientError("transient", adapter_name="test"),
        SourceParseError("parse failed", adapter_name="test"),
    ]

    for error in errors:
        try:
            raise error
        except SourceError as e:
            assert e.adapter_name == "test"
        else:
            pytest.fail(f"Expected SourceError to be caught for {type(error)}")


def test_catch_specific_error_type() -> None:
    """Callers can catch specific error types for fine-grained handling."""
    try:
        raise SourceRateLimitError("rate limit", adapter_name="test", retry_after=60.0)
    except SourceRateLimitError as e:
        assert e.retry_after == 60.0
    except SourceError:
        pytest.fail("Expected SourceRateLimitError to be caught specifically")
