"""Tests for Statuspage incident update publishing."""

from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.statuspage_incident_updates import (
    StatuspageIncidentUpdatePublishError,
    StatuspageIncidentUpdatePublisher,
)


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"system": "max", "type": "idea", "idea_id": "bu-sp001"},
        "project": {
            "title": "Statuspage Publisher",
            "summary": "Publish customer-facing incident updates.",
        },
        "execution": {"validation_plan": "Create a sandbox update."},
    }


def _design_brief_packet() -> dict:
    return {
        "design_brief": {
            "id": "dbf-sp001",
            "title": "Statuspage Brief",
            "lead_idea_id": "bu-sp001",
            "source_idea_ids": ["bu-sp001"],
            "readiness_score": 87.0,
            "design_status": "ready",
            "merged_product_concept": "Turn design brief handoffs into incident updates.",
        }
    }


def test_dry_run_builds_deterministic_update_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = StatuspageIncidentUpdatePublisher(
        page_id="page123",
        incident_id="inc123",
        status="monitoring",
        body="Max incident update",
        deliver_notifications=False,
        client=client,
    )

    first = publisher.publish(_tact_spec(), dry_run=True)
    second = publisher.publish(_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.update_id is None
    assert first.endpoint == (
        "https://api.statuspage.io/v1/pages/page123/incidents/inc123/incident_updates"
    )
    assert first.payload["body"] == "Max incident update"
    assert first.payload["status"] == "monitoring"
    assert first.payload["deliver_notifications"] is False
    assert first.payload["metadata"]["publisher"] == "max.statuspage_incident_updates"


def test_design_brief_dry_run_builds_update_from_persisted_packet() -> None:
    publisher = StatuspageIncidentUpdatePublisher(page_id="page123", incident_id="inc123")

    result = publisher.publish_design_brief(
        _design_brief_packet(),
        markdown="# Statuspage Brief",
        dry_run=True,
    )

    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["design_brief_id"] == "dbf-sp001"
    assert "Statuspage Brief" in result.payload["body"]


def test_live_publish_posts_incident_update_and_returns_id() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"incident_update": {"id": "upd123"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = StatuspageIncidentUpdatePublisher(
        page_id="page123",
        incident_id="inc123",
        api_key="sp-secret",
        api_url="https://statuspage.example.test",
        body="Max incident update",
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.update_id == "upd123"
    assert requests[0].url == (
        "https://statuspage.example.test/v1/pages/page123/incidents/inc123/incident_updates"
    )
    assert requests[0].headers["Authorization"] == "OAuth sp-secret"
    assert requests[0].headers["Content-Type"] == "application/json"
    assert json.loads(requests[0].read()) == {
        "incident_update": {"body": "Max incident update", "status": "investigating"}
    }


def test_from_env_reads_statuspage_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATUSPAGE_API_KEY", "env-key")
    monkeypatch.setenv("STATUSPAGE_PAGE_ID", "page-env")
    monkeypatch.setenv("STATUSPAGE_INCIDENT_ID", "incident-env")
    monkeypatch.setenv("STATUSPAGE_INCIDENT_STATUS", "resolved")
    monkeypatch.setenv("STATUSPAGE_DELIVER_NOTIFICATIONS", "true")

    publisher = StatuspageIncidentUpdatePublisher.from_env()

    assert publisher.api_key == "env-key"
    assert publisher.page_id == "page-env"
    assert publisher.incident_id == "incident-env"
    assert publisher.status == "resolved"
    assert publisher.deliver_notifications is True


def test_live_publish_requires_api_key() -> None:
    publisher = StatuspageIncidentUpdatePublisher(page_id="page123", incident_id="inc123")

    with pytest.raises(StatuspageIncidentUpdatePublishError, match="STATUSPAGE_API_KEY"):
        publisher.publish(_tact_spec(), dry_run=False)


def test_error_redacts_secret_and_includes_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="bad sp-secret Bearer sp-secret")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = StatuspageIncidentUpdatePublisher(
        page_id="page123",
        incident_id="inc123",
        api_key="sp-secret",
        client=client,
    )

    with pytest.raises(StatuspageIncidentUpdatePublishError, match="HTTP 401") as exc:
        publisher.publish(_tact_spec(), dry_run=False)

    assert exc.value.status_code == 401
    assert "sp-secret" not in str(exc.value)
    assert "[REDACTED]" in str(exc.value)
