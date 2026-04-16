"""Structured exception hierarchy for source adapter failures.

This module defines typed exceptions that allow callers to distinguish between
retriable and non-retriable errors when fetching signals from external sources.
"""

from __future__ import annotations


class SourceError(Exception):
    """Base exception for all source adapter errors.

    Attributes:
        adapter_name: Name of the adapter that raised the error (e.g., 'github_issues').
        message: Human-readable error message.
    """

    def __init__(self, message: str, *, adapter_name: str | None = None) -> None:
        self.adapter_name = adapter_name
        self.message = message
        super().__init__(message)

    def __str__(self) -> str:
        if self.adapter_name:
            return f"{self.adapter_name}: {self.message}"
        return self.message


class SourceRateLimitError(SourceError):
    """Raised when a source returns HTTP 429 or explicit rate-limit response.

    This error is retriable with exponential backoff. The `retry_after` field
    indicates the recommended delay before retrying (if provided by the source).

    Attributes:
        retry_after: Seconds to wait before retrying (None if not specified).
    """

    def __init__(
        self,
        message: str,
        *,
        adapter_name: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, adapter_name=adapter_name)
        self.retry_after = retry_after


class SourceAuthError(SourceError):
    """Raised when a source returns HTTP 401 (Unauthorized) or 403 (Forbidden).

    This error is non-retriable without changing credentials or permissions.
    """

    pass


class SourceTransientError(SourceError):
    """Raised for transient network or server failures.

    Includes:
    - HTTP 5xx server errors (500, 502, 503, 504)
    - Connection timeouts
    - Connection resets
    - DNS resolution failures

    This error is retriable with backoff.

    Attributes:
        retry_after: Suggested delay before retrying (None if not specified).
    """

    def __init__(
        self,
        message: str,
        *,
        adapter_name: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, adapter_name=adapter_name)
        self.retry_after = retry_after


class SourceParseError(SourceError):
    """Raised when a source returns malformed or unparseable data.

    Includes:
    - Invalid JSON
    - Malformed XML/RSS
    - Missing required fields in response
    - Unexpected data structure

    This error is non-retriable — the source data is broken and retrying
    will not help.
    """

    pass
