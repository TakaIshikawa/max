"""Tests for Freshdesk ticket publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import FreshdeskTicketPublisher as ExportedFreshdeskTicketPublisher
from max.publisher.freshdesk_tickets import (
    FreshdeskTicketPublishError,
    FreshdeskTicketPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-freshdesk001",
            "status": "approved",
            "domain": "devtools",
            "category": "support_ops",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "Freshdesk Ticket Publisher",
            "summary": "Publish implementation-ready specs into Freshdesk",
            "target_users": "support operations teams",
        },
        "problem": {"statement": "Generated specs do not reach support queues."},
        "solution": {"approach": "Create Freshdesk tickets through the REST API."},
        "execution": {
            "mvp_scope": ["Ticket payload builder", "Live publisher"],
            "validation_plan": "Publish one approved spec into a sandbox Freshdesk account.",
        },
        "evidence": {
            "rationale": "Teams operationalize handoffs in support tools.",
            "insight_ids": ["ins-freshdesk001"],
            "signal_ids": ["sig-freshdesk001"],
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


def test_dry_run_returns_freshdesk_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = FreshdeskTicketPublisher(
        "acme",
        api_key="freshdesk_api_key",
        requester_email="handoff@example.com",
        product_id=123,
        tags=["internal handoff"],
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.dry_run is True
    assert result.status_code is None
    assert result.ticket_id is None
    assert result.ticket_url is None
    assert result.payload["subject"] == "[Max] Freshdesk Ticket Publisher"
    assert result.payload["priority"] == 2
    assert result.payload["status"] == 2
    assert result.payload["email"] == "handoff@example.com"
    assert result.payload["product_id"] == 123
    assert "tact-spec" in result.payload["tags"]
    assert "support-ops" in result.payload["tags"]
    assert "internal-handoff" in result.payload["tags"]
    assert result.payload["custom_fields"]["cf_max_idea_id"] == "bu-freshdesk001"
    assert result.payload["metadata"]["publisher"] == "max.freshdesk_tickets"
    assert "Publish one approved spec" in result.payload["description"]


def test_live_publish_posts_ticket_with_auth_and_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"id": 42})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = FreshdeskTicketPublisher(
        "acme.freshdesk.com",
        api_key="freshdesk_api_key",
        requester_email="handoff@example.com",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.ticket_id == "42"
    assert result.ticket_url == "https://acme.freshdesk.com/a/tickets/42"
    assert requests[0].url == "https://acme.freshdesk.com/api/v2/tickets"
    expected_auth = base64.b64encode(b"freshdesk_api_key:X").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert requests[0].headers["User-Agent"] == "max-freshdesk-tickets-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["subject"] == "[Max] Freshdesk Ticket Publisher"
    assert posted["email"] == "handoff@example.com"
    assert posted["custom_fields"]["cf_max_schema_version"] == "tact-spec-preview/v1"
    assert "metadata" not in posted
    assert result.payload["metadata"]["freshdesk_ticket_id"] == "42"


def test_from_env_reads_freshdesk_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRESHDESK_DOMAIN", "env-helpdesk")
    monkeypatch.setenv("FRESHDESK_API_KEY", "env_key")
    monkeypatch.setenv("FRESHDESK_REQUESTER_EMAIL", "env@example.com")
    monkeypatch.setenv("FRESHDESK_PRODUCT_ID", "987")
    monkeypatch.setenv("FRESHDESK_TAGS", "ops, internal handoff")
    monkeypatch.setenv("FRESHDESK_PRIORITY", "3")
    monkeypatch.setenv("FRESHDESK_STATUS", "2")

    publisher = FreshdeskTicketPublisher.from_env()

    assert publisher.domain == "env-helpdesk.freshdesk.com"
    assert publisher.api_key == "env_key"
    assert publisher.requester_email == "env@example.com"
    assert publisher.product_id == 987
    assert publisher.tags == ["ops", "internal-handoff"]
    assert publisher.priority == 3
    assert publisher.status == 2


def test_live_publish_requires_api_key() -> None:
    publisher = FreshdeskTicketPublisher("acme")

    with pytest.raises(FreshdeskTicketPublishError, match="FRESHDESK_API_KEY"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_build_ticket_payload_validates_tact_spec_input() -> None:
    publisher = FreshdeskTicketPublisher("acme")

    with pytest.raises(FreshdeskTicketPublishError, match="schema_version"):
        publisher.build_ticket_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(FreshdeskTicketPublishError, match="project.title"):
        publisher.build_ticket_payload({"schema_version": "tact-spec-preview/v1"})


def test_live_publish_raises_error_with_status_code_on_non_2xx() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, json={"message": "Forbidden"})
        )
    )
    publisher = FreshdeskTicketPublisher(
        "acme",
        api_key="freshdesk_api_key",
        client=client,
    )

    with pytest.raises(FreshdeskTicketPublishError, match="HTTP 403") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 403


def test_exported_from_publisher_package() -> None:
    assert ExportedFreshdeskTicketPublisher is FreshdeskTicketPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
