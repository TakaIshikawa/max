"""Tests for email webhook publishing."""

from __future__ import annotations

import logging

import httpx
import pytest

from max.publisher.email_webhook import (
    EmailWebhookPublishError,
    EmailWebhookPublisher,
)


def _max_payload() -> dict[str, object]:
    return {
        "schema_version": "max.test.v1",
        "kind": "design_brief",
        "project": {"title": "Email Automation"},
        "source": {"idea_id": "idea_123", "system": "max"},
        "metadata": {"domain": "ops"},
    }


def test_build_payload_includes_email_fields_and_metadata() -> None:
    publisher = EmailWebhookPublisher(
        "https://mailer.example.com/hooks/max",
        recipient="team@example.com",
        subject_template="{payload_type}: {title}",
        payload_type="design-brief",
    )

    payload = publisher.build_payload(
        _max_payload(),
        text_body="Plain text summary",
        markdown_body="# Markdown summary",
        metadata={"run_id": "run_456"},
    ).to_dict()

    assert payload["to"] == "team@example.com"
    assert payload["subject"] == "design-brief: Email Automation"
    assert payload["body"] == {
        "text": "Plain text summary",
        "markdown": "# Markdown summary",
    }
    assert payload["payload_type"] == "design-brief"
    assert payload["metadata"]["publisher"] == "max.email_webhook"
    assert payload["metadata"]["schema_version"] == "max.test.v1"
    assert payload["metadata"]["source_id"] == "idea_123"
    assert payload["metadata"]["domain"] == "ops"
    assert payload["metadata"]["run_id"] == "run_456"


def test_publish_posts_json_email_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"ok": True})

    publisher = EmailWebhookPublisher(
        "https://mailer.example.com/hooks/max",
        recipient="team@example.com",
        payload_type="brief-email",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    result = publisher.publish(_max_payload(), markdown_body="# Brief")

    assert result.status_code == 202
    assert result.attempts == 1
    assert result.payload["body"] == {"markdown": "# Brief"}
    assert requests[0].method == "POST"
    assert requests[0].headers["X-Max-Payload-Type"] == "brief-email"
    assert requests[0].read() == (
        b'{"to":"team@example.com","subject":"[Max] Email Automation",'
        b'"body":{"markdown":"# Brief"},"payload_type":"brief-email",'
        b'"metadata":{"publisher":"max.email_webhook","payload_type":"brief-email",'
        b'"schema_version":"max.test.v1","kind":"design_brief",'
        b'"source_id":"idea_123","domain":"ops"}}'
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"recipient": ""}, "recipient is required"),
        (
            {"recipient": "team@example.com", "text_body": ""},
            "requires text_body or markdown_body",
        ),
    ],
)
def test_publish_validates_required_fields(
    kwargs: dict[str, str],
    message: str,
) -> None:
    publisher = EmailWebhookPublisher("https://mailer.example.com/hooks/max")

    with pytest.raises(EmailWebhookPublishError, match=message):
        publisher.publish(_max_payload(), **kwargs)


def test_invalid_webhook_url_is_rejected() -> None:
    with pytest.raises(EmailWebhookPublishError, match="absolute http\\(s\\) URL"):
        EmailWebhookPublisher("not-a-url", recipient="team@example.com")


def test_publish_retries_transient_status_and_succeeds() -> None:
    statuses = [503, 200]
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        seen.append(status)
        return httpx.Response(status, json={"ok": True})

    publisher = EmailWebhookPublisher(
        "https://mailer.example.com/hooks/max",
        recipient="team@example.com",
        retries=1,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    result = publisher.publish(_max_payload(), text_body="Summary")

    assert result.status_code == 200
    assert result.attempts == 2
    assert seen == [503, 200]


def test_publish_failure_redacts_url_secrets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False})

    publisher = EmailWebhookPublisher(
        "https://user:password@mailer.example.com/hooks/max?token=secret-token",
        recipient="team@example.com",
        retries=0,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )

    with pytest.raises(EmailWebhookPublishError) as exc_info:
        publisher.publish(_max_payload(), text_body="Summary")

    message = str(exc_info.value)
    assert "https://***@mailer.example.com/hooks/max?[redacted]" in message
    assert "password" not in message
    assert "secret-token" not in message


def test_redacted_logging_does_not_emit_secret_url_parts(caplog) -> None:
    publisher = EmailWebhookPublisher(
        "https://user:password@mailer.example.com/hooks/max?token=secret-token",
        recipient="team@example.com",
        client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(204))
        ),
        sleep=lambda _: None,
    )

    with caplog.at_level(logging.INFO, logger="max.publisher.webhook"):
        publisher.publish(_max_payload(), text_body="Summary")

    assert "https://***@mailer.example.com/hooks/max?[redacted]" in caplog.text
    assert "password" not in caplog.text
    assert "secret-token" not in caplog.text
