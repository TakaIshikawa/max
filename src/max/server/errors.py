"""Structured exception hierarchy for MCP tools server errors.

This module defines typed exceptions that enable callers to distinguish between
different failure modes when using MCP tools, making debugging easier and
improving API usability.
"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    """HTTP-style error codes for MCP tool errors."""

    INVALID_INPUT = 400
    NOT_FOUND = 404
    STATE_CONFLICT = 409
    RATE_LIMITED = 429
    EXTERNAL_SERVICE_UNAVAILABLE = 502


class MCPToolError(Exception):
    """Base exception for all MCP tool errors.

    Attributes:
        message: Human-readable error message.
        code: Error code indicating the type of failure.
        details: Additional context about the error (field names, suggestions, etc.).
    """

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict:
        """Convert exception to error response dict."""
        return {
            "error": self.message,
            "code": int(self.code) if self.code else None,
            "details": self.details,
        }


class ValidationError(MCPToolError):
    """Raised when input validation fails.

    Includes:
    - Invalid parameter types
    - Out-of-range values
    - Missing required fields
    - Invalid field combinations

    Attributes:
        field: Name of the field that failed validation (if applicable).
        expected: Description of expected value format.
        actual: The actual value provided.
    """

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        expected: str | None = None,
        actual: str | None = None,
        details: dict | None = None,
    ) -> None:
        error_details = details or {}
        if field:
            error_details["field"] = field
        if expected:
            error_details["expected"] = expected
        if actual:
            error_details["actual"] = actual

        super().__init__(message, code=ErrorCode.INVALID_INPUT, details=error_details)


class ResourceNotFoundError(MCPToolError):
    """Raised when a requested resource does not exist.

    Includes:
    - Missing ideas (buildable units)
    - Missing profiles
    - Missing design briefs
    - Missing evaluations

    Attributes:
        resource_type: Type of resource that was not found.
        resource_id: ID of the missing resource.
    """

    def __init__(
        self,
        message: str,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        error_details = details or {}
        if resource_type:
            error_details["resource_type"] = resource_type
        if resource_id:
            error_details["resource_id"] = resource_id

        super().__init__(message, code=ErrorCode.NOT_FOUND, details=error_details)


class RateLimitError(MCPToolError):
    """Raised when rate limits or quotas are exceeded.

    This error is retriable with exponential backoff. The `retry_after` field
    indicates the recommended delay before retrying (if provided).

    Attributes:
        retry_after: Seconds to wait before retrying (None if not specified).
    """

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        details: dict | None = None,
    ) -> None:
        error_details = details or {}
        if retry_after is not None:
            error_details["retry_after"] = retry_after

        super().__init__(message, code=ErrorCode.RATE_LIMITED, details=error_details)


class ExternalServiceError(MCPToolError):
    """Raised when external services (LLM, embeddings) fail.

    Includes:
    - LLM API failures
    - Embeddings service unavailable
    - External API timeouts
    - Network failures

    This error is retriable with backoff.

    Attributes:
        service: Name of the external service that failed.
        retry_after: Suggested delay before retrying (None if not specified).
    """

    def __init__(
        self,
        message: str,
        *,
        service: str | None = None,
        retry_after: float | None = None,
        details: dict | None = None,
    ) -> None:
        error_details = details or {}
        if service:
            error_details["service"] = service
        if retry_after is not None:
            error_details["retry_after"] = retry_after

        super().__init__(
            message, code=ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE, details=error_details
        )


class StateConflictError(MCPToolError):
    """Raised when concurrent modifications or invalid state transitions occur.

    Includes:
    - Concurrent updates to the same resource
    - Invalid status transitions
    - Conflicting operations
    - Precondition failures

    Attributes:
        current_state: The current state of the resource.
        attempted_state: The state transition that was attempted.
    """

    def __init__(
        self,
        message: str,
        *,
        current_state: str | None = None,
        attempted_state: str | None = None,
        details: dict | None = None,
    ) -> None:
        error_details = details or {}
        if current_state:
            error_details["current_state"] = current_state
        if attempted_state:
            error_details["attempted_state"] = attempted_state

        super().__init__(message, code=ErrorCode.STATE_CONFLICT, details=error_details)
