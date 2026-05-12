from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.freshdesk_ticket_replies import (
    FreshdeskTicketReplyPublishError,
    FreshdeskTicketReplyPublisher,
)


def test_dry_run_builds_reply_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = FreshdeskTicketReplyPublisher(
        "acme",
        ticket_id="42",
        from_email="support@example.com",
        user_id=123,
        cc_emails=["ops@example.com"],
        attachments=[{"name": "runbook.txt", "content_type": "text/plain"}],
        client=client,
    )

    result = publisher.publish(body="<p>We restarted the worker pool.</p>", dry_run=True)

    assert result.status_code is None
    assert result.ticket_id == "42"
    assert result.conversation_id is None
    assert result.body_preview == "<p>We restarted the worker pool.</p>"
    assert result.payload["from_email"] == "support@example.com"
    assert result.payload["user_id"] == 123
    assert result.payload["cc_emails"] == ["ops@example.com"]
    assert result.payload["attachments"] == [{"name": "runbook.txt", "content_type": "text/plain"}]
    assert result.payload["metadata"]["publisher"] == "max.freshdesk_ticket_replies"


def test_live_publish_posts_reply_with_auth_and_returns_summary() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 987})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = FreshdeskTicketReplyPublisher(
        "acme.freshdesk.com",
        ticket_id="42",
        api_key="freshdesk-key",
        from_email="support@example.com",
        client=client,
    )

    result = publisher.publish(body="<p>Reply body</p>", cc_emails=["ops@example.com"], dry_run=False)

    assert result.status_code == 201
    assert result.ticket_id == "42"
    assert result.conversation_id == "987"
    assert requests[0].url == "https://acme.freshdesk.com/api/v2/tickets/42/reply"
    expected_auth = base64.b64encode(b"freshdesk-key:X").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    posted = json.loads(requests[0].read())
    assert posted == {
        "body": "<p>Reply body</p>",
        "from_email": "support@example.com",
        "cc_emails": ["ops@example.com"],
    }
    assert result.payload["metadata"]["freshdesk_conversation_id"] == "987"
    assert result.payload["metadata"]["api_status"] == 201


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRESHDESK_DOMAIN", "env-helpdesk")
    monkeypatch.setenv("FRESHDESK_TICKET_ID", "123")
    monkeypatch.setenv("FRESHDESK_API_KEY", "env-key")
    monkeypatch.setenv("FRESHDESK_FROM_EMAIL", "support-env@example.com")
    monkeypatch.setenv("FRESHDESK_USER_ID", "456")
    monkeypatch.setenv("FRESHDESK_CC_EMAILS", "ops@example.com,lead@example.com")

    publisher = FreshdeskTicketReplyPublisher.from_env()

    assert publisher.domain == "env-helpdesk.freshdesk.com"
    assert publisher.ticket_id == "123"
    assert publisher.api_key == "env-key"
    assert publisher.from_email == "support-env@example.com"
    assert publisher.user_id == 456
    assert publisher.cc_emails == ["ops@example.com", "lead@example.com"]


def test_live_publish_requires_api_key() -> None:
    publisher = FreshdeskTicketReplyPublisher("acme", ticket_id="42")

    with pytest.raises(FreshdeskTicketReplyPublishError, match="FRESHDESK_API_KEY"):
        publisher.publish(body="Reply body", dry_run=False)
