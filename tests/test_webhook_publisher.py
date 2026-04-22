"""Tests for webhook publishing."""

from __future__ import annotations

import logging

import httpx
import pytest

from max.publisher.webhook import WebhookPublishError, WebhookPublisher, redact_url


def test_publish_posts_json_payload_and_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebhookPublisher(
        "https://example.com/hooks/max",
        client=client,
        sleep=lambda _: None,
    )

    result = publisher.publish({"schema_version": "test.v1"}, payload_type="tact-spec")

    assert result.status_code == 202
    assert result.attempts == 1
    assert requests[0].method == "POST"
    assert requests[0].headers["X-Max-Payload-Type"] == "tact-spec"
    assert requests[0].read() == b'{"schema_version":"test.v1"}'


def test_publish_retries_transient_status_and_succeeds() -> None:
    statuses = [500, 200]
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        seen.append(status)
        return httpx.Response(status, json={"ok": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebhookPublisher(
        "https://example.com/hooks/max",
        retries=1,
        client=client,
        sleep=lambda _: None,
    )

    result = publisher.publish({"payload": "value"}, payload_type="blueprint")

    assert result.status_code == 200
    assert result.attempts == 2
    assert seen == [500, 200]


def test_publish_does_not_retry_validation_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad payload"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebhookPublisher(
        "https://example.com/hooks/max",
        retries=3,
        client=client,
        sleep=lambda _: None,
    )

    with pytest.raises(WebhookPublishError, match="HTTP 400"):
        publisher.publish({"payload": "value"}, payload_type="tact-spec")

    assert calls == 1


def test_publish_retries_request_errors_then_fails_with_redacted_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = WebhookPublisher(
        "https://user:secret@example.com/hooks/max?token=secret-token",
        retries=1,
        client=client,
        sleep=lambda _: None,
    )

    with pytest.raises(WebhookPublishError) as exc_info:
        publisher.publish({"payload": "value"}, payload_type="tact-spec")

    message = str(exc_info.value)
    assert "https://***@example.com/hooks/max?[redacted]" in message
    assert "secret-token" not in message
    assert "user:secret" not in message


def test_publish_validates_json_rejection_body() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": False}))
    )
    publisher = WebhookPublisher(
        "https://example.com/hooks/max",
        client=client,
        sleep=lambda _: None,
    )

    with pytest.raises(WebhookPublishError, match="rejected payload"):
        publisher.publish({"payload": "value"}, payload_type="blueprint")


def test_redacted_logging_does_not_emit_secret_url_parts(caplog) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(204)))
    publisher = WebhookPublisher(
        "https://user:password@example.com/hooks/max?api_key=secret",
        client=client,
        sleep=lambda _: None,
    )

    with caplog.at_level(logging.INFO, logger="max.publisher.webhook"):
        publisher.publish({"payload": "value"}, payload_type="tact-spec")

    assert "https://***@example.com/hooks/max?[redacted]" in caplog.text
    assert "password" not in caplog.text
    assert "api_key=secret" not in caplog.text


def test_redact_url_preserves_safe_location_parts() -> None:
    assert (
        redact_url("https://user:pass@example.com:8443/hooks/max?token=abc#frag")
        == "https://***@example.com:8443/hooks/max?[redacted]#[redacted]"
    )
