"""Tests for PagerDuty incident comment publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.pagerduty_incident_comments import (
    PagerDutyIncidentCommentPayload,
    PagerDutyIncidentCommentPublishError,
    PagerDutyIncidentCommentPublishResult,
    PagerDutyIncidentCommentPublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-pd-note001",
            "status": "approved",
            "domain": "platform",
            "category": "incident-management",
        },
        "project": {
            "title": "PagerDuty Incident Comment Publisher",
            "summary": "Post Max operational handoffs into PagerDuty incident notes.",
        },
        "problem": {"statement": "Responders lose launch context."},
        "solution": {"approach": "Append concise Max notes to PagerDuty incidents."},
        "execution": {
            "validation_plan": "Dry-run payloads before posting notes.",
            "mvp_scope": ["payload builder", "live note publisher"],
        },
        "evidence": {
            "rationale": "Incident commanders need responder-readable context.",
            "insight_ids": ["ins-pd-note001"],
            "signal_ids": ["sig-pd-note001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {"quality_score": 8.5, "novelty_score": 7.0, "usefulness_score": 9.0},
        "evaluation": {"overall_score": 84.0, "recommendation": "ship"},
    }


def _design_brief_packet() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-pd-note001",
            "title": "PagerDuty Note Brief",
            "domain": "platform",
            "theme": "incident-management",
            "lead_idea_id": "bu-pd-note001",
            "source_idea_ids": ["bu-pd-note001", "bu-supporting"],
            "readiness_score": 91.0,
            "design_status": "ready",
            "merged_product_concept": "Publish Max design briefs into PagerDuty notes.",
            "validation_plan": "Post one sandbox note.",
        },
    }


def test_exports_class_and_dataclasses() -> None:
    assert PagerDutyIncidentCommentPublisher.__name__ == "PagerDutyIncidentCommentPublisher"
    assert PagerDutyIncidentCommentPayload.__name__ == "PagerDutyIncidentCommentPayload"
    assert PagerDutyIncidentCommentPublishResult.__name__ == "PagerDutyIncidentCommentPublishResult"


def test_dry_run_returns_stable_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentCommentPublisher(
        incident_id="PINC123",
        note_body="Max handoff note",
        client=client,
    )

    first = publisher.publish(_tact_spec(), dry_run=True)
    second = publisher.publish(_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.status_code is None
    assert first.note_id is None
    assert first.endpoint == "https://api.pagerduty.com/incidents/PINC123/notes"
    assert first.payload == {
        "incident_id": "PINC123",
        "content": "Max handoff note",
        "metadata": {
            "publisher": "max.pagerduty_incident_comments",
            "source_system": "max",
            "source_type": "idea",
            "source_id": "bu-pd-note001",
            "idea_id": "bu-pd-note001",
            "design_brief_id": None,
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "pagerduty_incident_id": "PINC123",
        },
    }


def test_design_brief_dry_run_builds_note_from_persisted_packet() -> None:
    publisher = PagerDutyIncidentCommentPublisher(incident_id="PINC123")

    result = publisher.publish_design_brief(
        _design_brief_packet(),
        markdown="# PagerDuty Note Brief",
        dry_run=True,
    )

    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-pd-note001"
    assert "# PagerDuty Note Brief" in result.payload["content"]
    assert "Readiness" not in result.payload["content"]


def test_live_publish_posts_note_with_pagerduty_v2_headers_and_returns_note_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"note": {"id": "PNOTE123", "content": "created"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentCommentPublisher(
        incident_id="PINC123",
        api_token="pd-token",
        from_email="max@example.test",
        api_url="https://api.pagerduty.test",
        note_body="Max handoff note",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.note_id == "PNOTE123"
    assert requests[0].url == "https://api.pagerduty.test/incidents/PINC123/notes"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["From"] == "max@example.test"
    assert requests[0].headers["Accept"] == "application/vnd.pagerduty+json;version=2"
    assert requests[0].headers["Content-Type"] == "application/json"
    assert json.loads(requests[0].read()) == {"note": {"content": "Max handoff note"}}


def test_from_env_reads_pagerduty_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGERDUTY_API_TOKEN", "env-token")
    monkeypatch.setenv("PAGERDUTY_FROM_EMAIL", "env@example.test")
    monkeypatch.setenv("PAGERDUTY_INCIDENT_ID", "PENV123")

    publisher = PagerDutyIncidentCommentPublisher.from_env()

    assert publisher.api_token == "env-token"
    assert publisher.from_email == "env@example.test"
    assert publisher.incident_id == "PENV123"


def test_live_publish_requires_auth() -> None:
    publisher = PagerDutyIncidentCommentPublisher(incident_id="PINC123")

    with pytest.raises(PagerDutyIncidentCommentPublishError, match="PAGERDUTY_API_TOKEN"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_validates_incident_id_and_tact_spec() -> None:
    publisher = PagerDutyIncidentCommentPublisher()

    with pytest.raises(PagerDutyIncidentCommentPublishError, match="incident_id is required"):
        publisher.publish(_tact_spec(), dry_run=True)

    with pytest.raises(PagerDutyIncidentCommentPublishError, match="schema_version"):
        publisher.publish({"project": {"title": "Missing schema"}}, incident_id="PINC123")


def test_non_success_response_raises_status_and_redacts_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="denied pd-token Authorization: Token token=pd-token")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentCommentPublisher(
        incident_id="PINC123",
        api_token="pd-token",
        from_email="max@example.test",
        client=client,
    )

    with pytest.raises(PagerDutyIncidentCommentPublishError, match="HTTP 403") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 403
    assert "pd-token" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
