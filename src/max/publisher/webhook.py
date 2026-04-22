"""Webhook publisher for generated Max payloads."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_RETRIES = 2
RETRYABLE_STATUS_CODES = {408, 429}


class WebhookPublishError(RuntimeError):
    """Raised when a webhook publish fails after validation or retries."""


@dataclass(frozen=True)
class WebhookPublishResult:
    """Summary of a successful webhook publish."""

    status_code: int
    attempts: int
    url: str
    response_body: str


class WebhookPublisher:
    """POST generated payloads to a configured webhook URL."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        retries: int = DEFAULT_RETRIES,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if retries < 0:
            raise ValueError("retries must be greater than or equal to 0")
        self.url = url
        self.timeout = timeout
        self.retries = retries
        self._client = client
        self._sleep = sleep

    @property
    def redacted_url(self) -> str:
        """Return the webhook URL with credentials and query values redacted."""
        return redact_url(self.url)

    def publish(self, payload: dict[str, Any], *, payload_type: str) -> WebhookPublishResult:
        """Publish a generated payload and validate the webhook response."""
        attempts_allowed = self.retries + 1
        last_error: Exception | None = None

        close_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            for attempt in range(1, attempts_allowed + 1):
                logger.info(
                    "Posting %s webhook payload to %s (attempt %s/%s)",
                    payload_type,
                    self.redacted_url,
                    attempt,
                    attempts_allowed,
                )
                try:
                    response = client.post(
                        self.url,
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "max-webhook-publisher/1",
                            "X-Max-Payload-Type": payload_type,
                            "X-Max-Published-At": datetime.now(timezone.utc).isoformat(),
                        },
                        timeout=self.timeout,
                    )
                    validation_error = _response_validation_error(response)
                    if validation_error is None:
                        logger.info(
                            "Webhook publish accepted by %s with status %s",
                            self.redacted_url,
                            response.status_code,
                        )
                        return WebhookPublishResult(
                            status_code=response.status_code,
                            attempts=attempt,
                            url=self.redacted_url,
                            response_body=_response_body_preview(response),
                        )

                    last_error = WebhookPublishError(validation_error)
                    if not _should_retry_status(response.status_code) or attempt == attempts_allowed:
                        break
                    logger.warning(
                        "Webhook publish to %s returned retryable status %s; retrying",
                        self.redacted_url,
                        response.status_code,
                    )
                except (httpx.RequestError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt == attempts_allowed:
                        break
                    logger.warning(
                        "Webhook publish to %s failed with %s; retrying",
                        self.redacted_url,
                        exc.__class__.__name__,
                    )

                self._sleep(min(2 ** (attempt - 1), 8))
        finally:
            if close_client:
                client.close()

        detail = str(last_error) if last_error else "unknown error"
        raise WebhookPublishError(
            f"Webhook publish failed for {self.redacted_url} after {attempts_allowed} "
            f"attempt(s): {detail}"
        )


def redact_url(url: str) -> str:
    """Redact credentials and query values from a URL before logging."""
    parts = urlsplit(url)
    hostname = parts.hostname or ""
    netloc = hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    if parts.username or parts.password:
        netloc = f"***@{netloc}"
    query = "[redacted]" if parts.query else ""
    return urlunsplit(
        SplitResult(
            scheme=parts.scheme,
            netloc=netloc,
            path=parts.path,
            query=query,
            fragment="[redacted]" if parts.fragment else "",
        )
    )


def _response_validation_error(response: httpx.Response) -> str | None:
    if not 200 <= response.status_code < 300:
        return f"webhook returned HTTP {response.status_code}: {_response_body_preview(response)}"

    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type.lower() or not response.content:
        return None

    try:
        body = response.json()
    except ValueError:
        return "webhook returned invalid JSON response"

    if isinstance(body, dict):
        for key in ("ok", "success"):
            if body.get(key) is False:
                return f"webhook rejected payload: {_response_body_preview(response)}"
    return None


def _should_retry_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUS_CODES or 500 <= status_code < 600


def _response_body_preview(response: httpx.Response, *, limit: int = 500) -> str:
    text = response.text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
