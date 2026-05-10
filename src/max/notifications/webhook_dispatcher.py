"""Generic webhook dispatcher for third-party integrations.

Supports sending event payloads to arbitrary webhook endpoints with configurable
authentication, retry logic, and error handling. Compatible with Zapier, IFTTT,
and custom webhook receivers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2.0


class WebhookDispatchError(RuntimeError):
    """Raised when a webhook dispatch cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retries_exhausted: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retries_exhausted = retries_exhausted


@dataclass(frozen=True)
class WebhookDispatchResult:
    """Summary of a webhook dispatch attempt."""

    status_code: int | None
    url: str
    dry_run: bool
    payload: dict[str, Any]
    headers: dict[str, str]
    response_body: str = ""
    attempts: int = 0
    total_duration_seconds: float = 0.0


class WebhookDispatcher:
    """Generic webhook dispatcher for third-party integrations.

    Supports:
    - Configurable HTTP methods (POST, PUT, PATCH)
    - Custom headers and authentication (Bearer, Basic, API Key)
    - Exponential backoff retries with configurable parameters
    - Dry-run mode for testing
    - Request/response logging

    Example:
        dispatcher = WebhookDispatcher(
            url="https://hooks.example.com/webhook",
            auth_type="bearer",
            auth_token="secret_token",
            max_retries=3,
        )
        result = dispatcher.dispatch({"event": "spec.created", "data": {...}})
    """

    def __init__(
        self,
        url: str,
        *,
        method: Literal["POST", "PUT", "PATCH"] = "POST",
        auth_type: Literal["none", "bearer", "basic", "api_key"] | None = None,
        auth_token: str | None = None,
        auth_username: str | None = None,
        auth_password: str | None = None,
        api_key_header: str = "X-API-Key",
        custom_headers: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        client: httpx.Client | None = None,
    ) -> None:
        """Initialize the webhook dispatcher.

        Args:
            url: Webhook endpoint URL
            method: HTTP method (POST, PUT, PATCH)
            auth_type: Authentication method (none, bearer, basic, api_key)
            auth_token: Token for bearer authentication
            auth_username: Username for basic authentication
            auth_password: Password for basic authentication
            api_key_header: Header name for API key authentication
            custom_headers: Additional headers to include in requests
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            backoff_base: Base for exponential backoff (delay = backoff_base ** attempt)
            client: Optional httpx.Client for dependency injection
        """
        if not url.strip():
            raise WebhookDispatchError("Webhook URL is required")

        self.url = url
        self.method = method
        self.auth_type = auth_type or "none"
        self.auth_token = auth_token
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.api_key_header = api_key_header
        self.custom_headers = custom_headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._client = client

    @property
    def redacted_url(self) -> str:
        """Return the webhook URL with query parameters redacted."""
        if "?" in self.url:
            base = self.url.split("?")[0]
            return f"{base}?[redacted]"
        return self.url

    def build_headers(self) -> dict[str, str]:
        """Build HTTP headers including authentication and custom headers."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "max-webhook-dispatcher/1.0",
            "X-Max-Dispatched-At": datetime.now(timezone.utc).isoformat(),
        }

        # Add authentication headers
        if self.auth_type == "bearer" and self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        elif self.auth_type == "api_key" and self.auth_token:
            headers[self.api_key_header] = self.auth_token
        # Basic auth is handled via httpx.Auth, not headers

        # Add custom headers (can override defaults)
        headers.update(self.custom_headers)

        return headers

    def dispatch(
        self,
        payload: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> WebhookDispatchResult:
        """Dispatch a webhook with the given payload.

        Args:
            payload: JSON-serializable payload to send
            dry_run: If True, build headers/payload but don't send request

        Returns:
            WebhookDispatchResult with status, response, and retry information

        Raises:
            WebhookDispatchError: If dispatch fails after all retries
        """
        headers = self.build_headers()

        if dry_run:
            return WebhookDispatchResult(
                status_code=None,
                url=self.redacted_url,
                dry_run=True,
                payload=payload,
                headers=headers,
                attempts=0,
            )

        # Prepare auth for basic authentication
        auth = None
        if self.auth_type == "basic" and self.auth_username and self.auth_password:
            auth = httpx.BasicAuth(self.auth_username, self.auth_password)

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)

        start_time = time.time()
        attempts = 0
        last_error: Exception | None = None

        try:
            for attempt in range(self.max_retries + 1):
                attempts = attempt + 1

                try:
                    response = client.request(
                        method=self.method,
                        url=self.url,
                        json=payload,
                        headers=headers,
                        auth=auth,
                        timeout=self.timeout,
                    )

                    # Success case
                    if 200 <= response.status_code < 300:
                        total_duration = time.time() - start_time
                        return WebhookDispatchResult(
                            status_code=response.status_code,
                            url=self.redacted_url,
                            dry_run=False,
                            payload=payload,
                            headers=headers,
                            response_body=_response_preview(response),
                            attempts=attempts,
                            total_duration_seconds=total_duration,
                        )

                    # Non-retryable error (4xx client errors)
                    if 400 <= response.status_code < 500:
                        raise WebhookDispatchError(
                            f"Webhook dispatch failed with HTTP {response.status_code}: "
                            f"{_response_preview(response)}",
                            status_code=response.status_code,
                            retries_exhausted=False,
                        )

                    # Retryable error (5xx server errors) - will retry
                    last_error = WebhookDispatchError(
                        f"Webhook dispatch failed with HTTP {response.status_code}: "
                        f"{_response_preview(response)}",
                        status_code=response.status_code,
                        retries_exhausted=True,
                    )

                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt == self.max_retries:
                        break

                # Exponential backoff before retry
                if attempt < self.max_retries:
                    delay = self.backoff_base ** attempt
                    time.sleep(delay)

            # All retries exhausted
            total_duration = time.time() - start_time
            error_msg = (
                f"Webhook dispatch to {self.redacted_url} failed after {attempts} attempts "
                f"({total_duration:.2f}s): {last_error}"
            )
            raise WebhookDispatchError(
                error_msg,
                status_code=getattr(last_error, "status_code", None),
                retries_exhausted=True,
            ) from last_error

        finally:
            if close_client:
                client.close()


def _response_preview(response: httpx.Response, *, limit: int = 500) -> str:
    """Extract a preview of the response body for logging."""
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
