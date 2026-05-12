"""Tests for Zendesk ticket note publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher.zendesk_ticket_notes import (
    ZendeskTicketNotePublishError,
    ZendeskTicketNotePublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-zendesk-note001",
            "status": "approved",
            "domain": "support",
            "category": "launch",
        },
        "project": {
            "title": "Zendesk Ticket Note Publisher",
            "summary": "Append launch decisions to existing Zendesk tickets.",
        },
        "execution": {
            "mvp_scope": ["Private ticket comment payload", "Live publisher"],
            "validation_plan": "Post one internal note to a sandbox ticket.",
        },
        "evidence": {
            "rationale": "Support teams need validation context on the ticket.",
            "insight_ids": ["ins-zendesk-note001"],
            "signal_ids": ["sig-zendesk-note001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["handoff_risk"],
        },
        "evaluation": {"overall_score": 82.0, "recommendation": "yes"},
    }


def test_builds_internal_note_payload_by_default() -> None:
    publisher = ZendeskTicketNotePublisher("acme", ticket_id="123")

    payload = publisher.build_note_payload(_tact_spec()).to_dict()

    assert payload["ticket_id"] == "123"
    assert payload["public"] is False
    assert "# Zendesk Ticket Note Publisher" in payload["body"]
    assert "- Idea ID: bu-zendesk-note001" in payload["body"]
    assert payload["metadata"]["publisher"] == "max.zendesk_ticket_notes"
    assert payload["metadata"]["zendesk_ticket_id"] == "123"


def test_note_body_override_is_used_in_payload() -> None:
    publisher = ZendeskTicketNotePublisher(
        "acme",
        ticket_id="123",
        note_body="Launch decision: hold until support staffing is confirmed.",
    )

    payload = publisher.build_note_payload(_tact_spec()).to_dict()

    assert payload["body"] == "Launch decision: hold until support staffing is confirmed."


def test_from_env_reads_zendesk_ticket_note_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "env-support")
    monkeypatch.setenv("ZENDESK_TICKET_ID", "456")
    monkeypatch.setenv("ZENDESK_EMAIL", "agent@example.com")
    monkeypatch.setenv("ZENDESK_API_TOKEN", "env_api_token")
    monkeypatch.setenv("ZENDESK_BEARER_TOKEN", "env_bearer_token")
    monkeypatch.setenv("ZENDESK_NOTE_BODY", "Env note")
    monkeypatch.setenv("ZENDESK_NOTE_PUBLIC", "true")

    publisher = ZendeskTicketNotePublisher.from_env(max_retries=4, timeout=3.0)

    assert publisher.api_url == "https://env-support.zendesk.com"
    assert publisher.ticket_id == "456"
    assert publisher.email == "agent@example.com"
    assert publisher.api_token == "env_api_token"
    assert publisher.bearer_token == "env_bearer_token"
    assert publisher.note_body == "Env note"
    assert publisher.public is True
    assert publisher.max_retries == 4
    assert publisher.timeout == 3.0


def test_dry_run_returns_endpoint_ticket_id_and_payload_without_credentials_or_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    publisher = ZendeskTicketNotePublisher(
        api_url="https://support.example.com",
        ticket_id="123",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.ticket_id == "123"
    assert result.endpoint == "https://support.example.com/api/v2/tickets/123.json"
    assert result.payload["public"] is False
    assert "Zendesk Ticket Note Publisher" in result.payload["body"]


def test_live_publish_supports_api_token_basic_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ticket": {"id": 123}})

    publisher = ZendeskTicketNotePublisher(
        "acme",
        ticket_id="123",
        email="agent@example.com",
        api_token="zendesk_api_token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    expected_auth = base64.b64encode(b"agent@example.com/token:zendesk_api_token").decode("ascii")
    assert result.status_code == 200
    assert result.response == {"ticket": {"id": 123}}
    assert requests[0].method == "PUT"
    assert requests[0].url == "https://acme.zendesk.com/api/v2/tickets/123.json"
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].headers["User-Agent"] == "max-zendesk-ticket-notes-publisher/1"
    posted = json.loads(requests[0].read())
    assert posted["ticket"]["comment"]["public"] is False
    assert "Zendesk Ticket Note Publisher" in posted["ticket"]["comment"]["body"]


def test_live_publish_supports_bearer_token_auth_and_public_override() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ticket": {"id": 123}})

    publisher = ZendeskTicketNotePublisher(
        api_url="https://support.example.com",
        ticket_id="123",
        bearer_token="zendesk_bearer",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False, public=True, note_body="Public launch note")

    assert result.status_code == 200
    assert requests[0].headers["Authorization"] == "Bearer zendesk_bearer"
    posted = json.loads(requests[0].read())
    assert posted == {"ticket": {"comment": {"body": "Public launch note", "public": True}}}


def test_retryable_failure_retries_and_exposes_status_code() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, text="temporarily unavailable zendesk_api_token")

    publisher = ZendeskTicketNotePublisher(
        "acme",
        ticket_id="123",
        email="agent@example.com",
        api_token="zendesk_api_token",
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ZendeskTicketNotePublishError, match="HTTP 503") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert calls == 3
    assert exc.value.status_code == 503
    assert "zendesk_api_token" not in str(exc.value)


def test_non_2xx_error_redacts_credentials_and_includes_status() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                401,
                json={"error": "bad Authorization: Bearer zendesk_bearer"},
            )
        )
    )
    publisher = ZendeskTicketNotePublisher(
        "acme",
        ticket_id="123",
        bearer_token="zendesk_bearer",
        client=client,
    )

    with pytest.raises(ZendeskTicketNotePublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "zendesk_bearer" not in str(exc.value)
    assert "Bearer [REDACTED]" in str(exc.value)


def test_live_publish_requires_credentials() -> None:
    publisher = ZendeskTicketNotePublisher("acme", ticket_id="123")

    with pytest.raises(ZendeskTicketNotePublishError, match="ZENDESK_EMAIL"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_missing_ticket_id_is_actionable() -> None:
    publisher = ZendeskTicketNotePublisher("acme", bearer_token="zendesk_bearer")

    with pytest.raises(ZendeskTicketNotePublishError, match="ZENDESK_TICKET_ID"):
        publisher.publish(_tact_spec(), dry_run=True)
