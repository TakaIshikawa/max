"""Tests for generic webhook dispatcher."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from max.notifications.webhook_dispatcher import (
    WebhookDispatchError,
    WebhookDispatcher,
    WebhookDispatchResult,
)


@pytest.fixture(autouse=True)
def webhook_sleep():
    with patch("max.notifications.webhook_dispatcher.time.sleep") as sleep:
        yield sleep


def _sample_event_payload() -> dict:
    """Sample event payload for testing."""
    return {
        "event_type": "spec.created",
        "event_id": "evt_123456",
        "timestamp": "2026-05-10T12:00:00Z",
        "data": {
            "spec_id": "spec-test-001",
            "title": "Test Spec",
            "status": "draft",
            "domain": "testing",
        },
    }


def test_dry_run_returns_payload_without_network_call() -> None:
    """Dry run should build headers and payload but not make network calls."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        auth_type="bearer",
        auth_token="test_token",
        client=client,
    )

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.attempts == 0
    assert result.payload["event_type"] == "spec.created"
    assert result.headers["Authorization"] == "Bearer test_token"
    assert result.headers["Content-Type"] == "application/json"
    assert "X-Max-Dispatched-At" in result.headers


def test_successful_post_request() -> None:
    """Should successfully POST payload to webhook endpoint."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"status": "received"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        method="POST",
        client=client,
    )

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert result.status_code == 200
    assert result.dry_run is False
    assert result.attempts == 1
    assert "status" in result.response_body
    assert "received" in result.response_body
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url == "https://hooks.example.com/webhook"
    posted = json.loads(requests[0].read())
    assert posted["event_type"] == "spec.created"


def test_bearer_authentication() -> None:
    """Should include Bearer token in Authorization header."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        auth_type="bearer",
        auth_token="secret_bearer_token",
        client=client,
    )

    dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert requests[0].headers["Authorization"] == "Bearer secret_bearer_token"


def test_api_key_authentication() -> None:
    """Should include API key in custom header."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        auth_type="api_key",
        auth_token="api_key_12345",
        api_key_header="X-Custom-API-Key",
        client=client,
    )

    dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert requests[0].headers["X-Custom-API-Key"] == "api_key_12345"


def test_basic_authentication() -> None:
    """Should use basic authentication with username and password."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        auth_type="basic",
        auth_username="testuser",
        auth_password="testpass",
        client=client,
    )

    dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    # Basic auth is handled by httpx and encoded in Authorization header
    assert "Authorization" in requests[0].headers
    assert requests[0].headers["Authorization"].startswith("Basic ")


def test_custom_headers() -> None:
    """Should include custom headers in request."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        custom_headers={
            "X-Custom-Header": "custom_value",
            "X-App-Version": "1.0.0",
        },
        client=client,
    )

    dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert requests[0].headers["X-Custom-Header"] == "custom_value"
    assert requests[0].headers["X-App-Version"] == "1.0.0"


def test_put_method() -> None:
    """Should support PUT HTTP method."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        method="PUT",
        client=client,
    )

    dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert requests[0].method == "PUT"


def test_patch_method() -> None:
    """Should support PATCH HTTP method."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        method="PATCH",
        client=client,
    )

    dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert requests[0].method == "PATCH"


def test_retries_on_5xx_server_error(webhook_sleep) -> None:
    """Should retry on 5xx server errors with exponential backoff."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        # Fail first 2 attempts, succeed on 3rd
        if len(requests) < 3:
            return httpx.Response(500, text="Internal Server Error")
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        max_retries=3,
        backoff_base=2.0,
        client=client,
    )

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert result.status_code == 200
    assert result.attempts == 3
    assert len(requests) == 3
    assert [call.args[0] for call in webhook_sleep.call_args_list] == [1.0, 2.0]


def test_retries_exhausted_on_repeated_5xx() -> None:
    """Should raise error after max retries on repeated 5xx errors."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, text="Service Unavailable")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        max_retries=2,
        backoff_base=1.1,  # Small backoff for faster test
        client=client,
    )

    with pytest.raises(WebhookDispatchError) as exc_info:
        dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert exc_info.value.retries_exhausted is True
    assert exc_info.value.status_code == 503
    assert "failed after 3 attempts" in str(exc_info.value)
    assert len(requests) == 3  # Initial + 2 retries


def test_no_retry_on_4xx_client_error() -> None:
    """Should not retry on 4xx client errors."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, text="Bad Request")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        max_retries=3,
        client=client,
    )

    with pytest.raises(WebhookDispatchError) as exc_info:
        dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert exc_info.value.status_code == 400
    assert exc_info.value.retries_exhausted is False
    assert "Bad Request" in str(exc_info.value)
    assert len(requests) == 1  # No retries


def test_retry_on_network_error() -> None:
    """Should retry on network errors."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) < 2:
            raise httpx.ConnectError("Connection failed")
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        max_retries=3,
        backoff_base=1.1,  # Small backoff for faster test
        client=client,
    )

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert result.status_code == 200
    assert result.attempts == 2
    assert len(requests) == 2


def test_network_error_retries_exhausted() -> None:
    """Should raise error after max retries on repeated network errors."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ConnectError("Connection failed")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        max_retries=2,
        backoff_base=1.1,
        client=client,
    )

    with pytest.raises(WebhookDispatchError) as exc_info:
        dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert exc_info.value.retries_exhausted is True
    assert "failed after 3 attempts" in str(exc_info.value)
    assert len(requests) == 3


def test_redacted_url_hides_query_params() -> None:
    """Should redact query parameters from URL in results."""
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook?secret=abc123&token=xyz789",
        client=client,
    )

    assert dispatcher.redacted_url == "https://hooks.example.com/webhook?[redacted]"

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=True)
    assert result.url == "https://hooks.example.com/webhook?[redacted]"


def test_requires_url() -> None:
    """Should raise error if URL is empty."""
    with pytest.raises(WebhookDispatchError) as exc_info:
        WebhookDispatcher("")

    assert "Webhook URL is required" in str(exc_info.value)


def test_response_body_preview_truncation() -> None:
    """Should truncate long response bodies."""
    long_body = "x" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=long_body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        client=client,
    )

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert len(result.response_body) <= 503  # 500 + "..."
    assert result.response_body.endswith("...")


def test_timeout_configuration() -> None:
    """Should store timeout configuration correctly."""
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        timeout=5.0,
    )

    assert dispatcher.timeout == 5.0


def test_tracks_total_duration(webhook_sleep) -> None:
    """Should track total duration including retries."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) < 2:
            return httpx.Response(500, text="error")
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = WebhookDispatcher(
        "https://hooks.example.com/webhook",
        max_retries=2,
        backoff_base=1.5,
        client=client,
    )

    result = dispatcher.dispatch(_sample_event_payload(), dry_run=False)

    assert result.total_duration_seconds > 0
    webhook_sleep.assert_called_once_with(1.0)
