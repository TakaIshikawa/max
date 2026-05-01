"""Tests for Zendesk ticket publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import ZendeskTicketPublisher as ExportedZendeskTicketPublisher
from max.publisher.zendesk_tickets import (
    ZendeskTicketPublishError,
    ZendeskTicketPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-zendesk001",
            "status": "approved",
            "domain": "support",
            "category": "support_ops",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Zendesk Ticket Publisher",
            "summary": "Publish implementation-ready specs into Zendesk",
            "target_users": "support operations teams",
        },
        "problem": {"statement": "Validated ideas do not reach support queues."},
        "solution": {"approach": "Create Zendesk tickets through the REST API."},
        "execution": {
            "mvp_scope": ["Ticket payload builder", "Live publisher"],
            "validation_plan": "Publish one approved spec into a Zendesk sandbox.",
        },
        "evidence": {
            "rationale": "Support teams operationalize handoffs in Zendesk.",
            "insight_ids": ["ins-zendesk001"],
            "signal_ids": ["sig-zendesk001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["handoff_risk"],
        },
        "evaluation": {
            "overall_score": 82.0,
            "recommendation": "yes",
        },
    }


def test_dry_run_returns_zendesk_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZendeskTicketPublisher(
        "acme",
        email="agent@example.com",
        api_token="zendesk_api_token",
        requester_email="handoff@example.com",
        priority="high",
        tags=["internal handoff"],
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.ticket_id is None
    assert result.ticket_url is None
    assert result.payload["subject"] == "[Max] Zendesk Ticket Publisher"
    assert result.payload["priority"] == "high"
    assert result.payload["requester_email"] == "handoff@example.com"
    assert "tact-spec" in result.payload["tags"]
    assert "support-ops" in result.payload["tags"]
    assert "internal-handoff" in result.payload["tags"]
    assert {"id": "max_idea_id", "value": "bu-zendesk001"} in result.payload["custom_fields"]
    assert result.payload["metadata"]["publisher"] == "max.zendesk_tickets"
    assert "Publish one approved spec" in result.payload["description"]


def test_live_publish_posts_ticket_with_auth_and_payload_shape() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"ticket": {"id": 42}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZendeskTicketPublisher(
        "acme.zendesk.com",
        email="agent@example.com",
        api_token="zendesk_api_token",
        requester_email="handoff@example.com",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.ticket_id == "42"
    assert result.ticket_url == "https://acme.zendesk.com/agent/tickets/42"
    assert requests[0].url == "https://acme.zendesk.com/api/v2/tickets.json"
    expected_auth = base64.b64encode(
        b"agent@example.com/token:zendesk_api_token"
    ).decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].headers["User-Agent"] == "max-zendesk-tickets-publisher/1"
    posted = _json_from_request(requests[0])
    ticket = posted["ticket"]
    assert ticket["subject"] == "[Max] Zendesk Ticket Publisher"
    assert ticket["comment"]["body"].startswith("# Zendesk Ticket Publisher")
    assert ticket["requester"] == {"email": "handoff@example.com"}
    assert ticket["priority"] == "normal"
    assert {"id": "max_schema_version", "value": "tact-spec-preview/v1"} in ticket[
        "custom_fields"
    ]
    assert "metadata" not in ticket
    assert result.payload["metadata"]["zendesk_ticket_id"] == "42"


def test_live_publish_uses_configurable_base_url() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"ticket": {"id": 84}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ZendeskTicketPublisher(
        base_url="https://support.example.com",
        email="agent@example.com",
        api_token="zendesk_api_token",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert requests[0].url == "https://support.example.com/api/v2/tickets.json"
    assert result.ticket_url == "https://support.example.com/agent/tickets/84"


def test_from_env_reads_zendesk_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENDESK_SUBDOMAIN", "env-support")
    monkeypatch.setenv("ZENDESK_EMAIL", "env@example.com")
    monkeypatch.setenv("ZENDESK_API_TOKEN", "env_token")
    monkeypatch.setenv("ZENDESK_REQUESTER_EMAIL", "requester@example.com")
    monkeypatch.setenv("ZENDESK_TAGS", "ops, internal handoff")
    monkeypatch.setenv("ZENDESK_PRIORITY", "urgent")

    publisher = ZendeskTicketPublisher.from_env()

    assert publisher.base_url == "https://env-support.zendesk.com"
    assert publisher.email == "env@example.com"
    assert publisher.api_token == "env_token"
    assert publisher.requester_email == "requester@example.com"
    assert publisher.tags == ["ops", "internal-handoff"]
    assert publisher.priority == "urgent"


def test_live_publish_requires_credentials() -> None:
    publisher = ZendeskTicketPublisher("acme")

    with pytest.raises(ZendeskTicketPublishError, match="ZENDESK_EMAIL"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_build_ticket_payload_validates_tact_spec_input() -> None:
    publisher = ZendeskTicketPublisher("acme")

    with pytest.raises(ZendeskTicketPublishError, match="schema_version"):
        publisher.build_ticket_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(ZendeskTicketPublishError, match="project.title"):
        publisher.build_ticket_payload({"schema_version": "tact-spec-preview/v1"})


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(422, json={"error": "Invalid requester"})
        )
    )
    publisher = ZendeskTicketPublisher(
        "acme",
        email="agent@example.com",
        api_token="zendesk_api_token",
        client=client,
    )

    with pytest.raises(ZendeskTicketPublishError, match="HTTP 422") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 422


def test_exported_from_publisher_package() -> None:
    assert ExportedZendeskTicketPublisher is ZendeskTicketPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
