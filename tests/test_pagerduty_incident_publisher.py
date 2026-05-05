"""Tests for PagerDuty incident publishing."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from max.publisher import PagerDutyIncidentPublisher as ExportedPagerDutyIncidentPublisher
from max.publisher.pagerduty_incidents import (
    PagerDutyIncidentPublishError,
    PagerDutyIncidentPublisher,
)


def _design_brief_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": "dbf-pagerduty001",
            "idea_id": "bu-pagerduty001",
            "status": "approved",
            "domain": "platform",
            "category": "observability",
            "url": "https://max.example.test/design-briefs/dbf-pagerduty001",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "PagerDuty Incident Publisher",
            "summary": "Escalate launch risks and observability handoffs into PagerDuty.",
            "target_users": "platform teams",
        },
        "problem": {"statement": "Generated operational risks do not reach responders."},
        "solution": {"approach": "Create PagerDuty Events API v2 trigger payloads."},
        "execution": {
            "mvp_scope": ["Payload builder", "Live publisher"],
            "validation_plan": "Publish one approved design brief into a PagerDuty sandbox.",
        },
        "evidence": {
            "rationale": "Operational risks need responder ownership before launch.",
            "insight_ids": ["ins-pagerduty001"],
            "signal_ids": ["sig-pagerduty001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["launch_risk"],
        },
        "evaluation": {
            "overall_score": 83.0,
            "recommendation": "yes",
        },
    }


def test_dry_run_returns_deterministic_incident_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentPublisher(
        routing_key="pd_routing_key",
        severity="critical",
        source="max://launch-risk",
        custom_details={"runbook_url": "https://runbooks.example.test/max"},
        client=client,
    )

    first = publisher.publish(_design_brief_tact_spec(), dry_run=True)
    second = publisher.publish(_design_brief_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.status_code is None
    assert first.incident_key is None
    assert first.dedup_key == "max:design-brief:bu-pagerduty001"
    assert first.payload["routing_key"] == "pd_routing_key"
    assert first.payload["event_action"] == "trigger"
    assert first.payload["dedup_key"] == "max:design-brief:bu-pagerduty001"
    assert first.payload["payload"]["summary"] == "[Max] Launch risk: PagerDuty Incident Publisher"
    assert first.payload["payload"]["severity"] == "critical"
    assert first.payload["payload"]["source"] == "max://launch-risk"
    assert first.payload["payload"]["custom_details"]["source_url"] == (
        "https://max.example.test/design-briefs/dbf-pagerduty001"
    )
    assert first.payload["payload"]["custom_details"]["runbook_url"] == (
        "https://runbooks.example.test/max"
    )
    assert first.payload["payload"]["custom_details"]["max_metadata"]["publisher"] == (
        "max.pagerduty_incidents"
    )
    assert first.payload["metadata"]["source_type"] == "design_brief"
    assert first.payload["metadata"]["source_id"] == "bu-pagerduty001"


def test_live_publish_posts_events_api_v2_trigger_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            202,
            json={"status": "success", "message": "Event processed", "dedup_key": "pd-dedup-123"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentPublisher(
        routing_key="pd_routing_key",
        events_api_url="https://events.eu.pagerduty.com/v2/enqueue",
        dedup_key="custom-dedup-key",
        severity="warning",
        client=client,
    )

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert result.status_code == 202
    assert result.dedup_key == "pd-dedup-123"
    assert result.incident_key == "pd-dedup-123"
    assert requests[0].url == "https://events.eu.pagerduty.com/v2/enqueue"
    assert requests[0].headers["User-Agent"] == "max-pagerduty-incidents-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["routing_key"] == "pd_routing_key"
    assert posted["event_action"] == "trigger"
    assert posted["dedup_key"] == "custom-dedup-key"
    assert posted["payload"]["summary"] == "[Max] Launch risk: PagerDuty Incident Publisher"
    assert posted["payload"]["severity"] == "warning"
    assert posted["payload"]["source"] == "max/design-brief/bu-pagerduty001"
    assert posted["payload"]["custom_details"]["recommendation"] == "yes"
    assert "metadata" not in posted
    assert result.payload["metadata"]["pagerduty_dedup_key"] == "pd-dedup-123"
    assert result.payload["metadata"]["pagerduty_incident_key"] == "pd-dedup-123"


def test_live_publish_uses_incident_key_when_present() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202,
            json={"dedup_key": "dedup-from-pagerduty", "incident_key": "incident-from-pagerduty"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentPublisher(routing_key="pd_routing_key", client=client)

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert result.dedup_key == "dedup-from-pagerduty"
    assert result.incident_key == "incident-from-pagerduty"


def test_provider_failures_raise_redacted_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            text=(
                "bad routing_key=pd_secret "
                "https://events.pagerduty.com/v2/enqueue?routing_key=url_secret&safe=yes"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentPublisher(
        routing_key="pd_secret",
        events_api_url="https://events.pagerduty.com?routing_key=site_secret",
        client=client,
    )

    with pytest.raises(PagerDutyIncidentPublishError) as exc:
        publisher.publish(_design_brief_tact_spec(), dry_run=False)

    message = str(exc.value)
    assert exc.value.status_code == 403
    assert "pd_secret" not in message
    assert "url_secret" not in message
    assert "site_secret" not in message
    assert "routing_key=%3Credacted%3E" in message


def test_from_env_reads_pagerduty_configuration_and_normalizes_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAGERDUTY_ROUTING_KEY", "env_routing_key")
    monkeypatch.setenv("PAGERDUTY_EVENTS_API_URL", "events.eu.pagerduty.com/v2/enqueue")
    monkeypatch.setenv("PAGERDUTY_EVENT_ACTION", "trigger")
    monkeypatch.setenv("PAGERDUTY_SEVERITY", "error")
    monkeypatch.setenv("PAGERDUTY_SOURCE", "max://ops")
    monkeypatch.setenv("PAGERDUTY_DEDUP_KEY", "env-dedup-key")

    publisher = PagerDutyIncidentPublisher.from_env()

    assert publisher.routing_key == "env_routing_key"
    assert publisher.events_api_url == "https://events.eu.pagerduty.com"
    assert publisher.enqueue_endpoint == "https://events.eu.pagerduty.com/v2/enqueue"
    assert publisher.event_action == "trigger"
    assert publisher.severity == "error"
    assert publisher.source == "max://ops"
    assert publisher.dedup_key == "env-dedup-key"


def test_live_publish_requires_routing_key() -> None:
    publisher = PagerDutyIncidentPublisher()

    with pytest.raises(PagerDutyIncidentPublishError, match="PAGERDUTY_ROUTING_KEY"):
        publisher.publish(_design_brief_tact_spec(), dry_run=False)


def test_build_incident_payload_validates_input() -> None:
    publisher = PagerDutyIncidentPublisher()

    with pytest.raises(PagerDutyIncidentPublishError, match="schema_version"):
        publisher.build_incident_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(PagerDutyIncidentPublishError, match="project.title"):
        publisher.build_incident_payload({"schema_version": "tact-spec-preview/v1"})

    with pytest.raises(PagerDutyIncidentPublishError, match="severity"):
        PagerDutyIncidentPublisher(severity="urgent")

    with pytest.raises(PagerDutyIncidentPublishError, match="custom_details"):
        invalid_custom_details: Any = ["not", "a", "dict"]
        PagerDutyIncidentPublisher(custom_details=invalid_custom_details)


def test_exported_from_publisher_package() -> None:
    assert ExportedPagerDutyIncidentPublisher is PagerDutyIncidentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
