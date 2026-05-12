from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.pagerduty_incident_status_updates import (
    PagerDutyIncidentStatusUpdatePublishError,
    PagerDutyIncidentStatusUpdatePublisher,
)


def test_dry_run_builds_status_update_payload() -> None:
    publisher = PagerDutyIncidentStatusUpdatePublisher(
        incident_id="PINC1",
        status="acknowledged",
        resolution_note="Resolved by rollback.",
    )

    result = publisher.publish(dry_run=True)

    assert result.status_code is None
    assert result.incident_id == "PINC1"
    assert result.status == "acknowledged"
    assert result.endpoint == "https://api.pagerduty.com/incidents/PINC1"
    assert result.payload == {
        "incident_id": "PINC1",
        "status": "acknowledged",
        "resolution_note": "Resolved by rollback.",
        "metadata": {
            "publisher": "max.pagerduty_incident_status_updates",
            "pagerduty_incident_id": "PINC1",
            "target_status": "acknowledged",
        },
    }


def test_live_publish_updates_incident_status_with_headers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"incident": {"id": "PINC1", "status": "resolved"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = PagerDutyIncidentStatusUpdatePublisher(
        incident_id="PINC1",
        status="resolved",
        api_token="pd-token",
        from_email="max@example.com",
        api_url="https://api.pagerduty.test",
        resolution_note="Resolved by rollback.",
        client=client,
    )

    result = publisher.publish(dry_run=False)

    assert result.status_code == 200
    assert result.status == "resolved"
    assert requests[0].url == "https://api.pagerduty.test/incidents/PINC1"
    assert requests[0].headers["Authorization"] == "Token token=pd-token"
    assert requests[0].headers["From"] == "max@example.com"
    assert requests[0].headers["Accept"] == "application/vnd.pagerduty+json;version=2"
    assert json.loads(requests[0].read()) == {
        "incident": {
            "type": "incident",
            "status": "resolved",
            "resolution": "Resolved by rollback.",
        }
    }


def test_from_env_reads_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGERDUTY_INCIDENT_ID", "PENV1")
    monkeypatch.setenv("PAGERDUTY_INCIDENT_STATUS", "acknowledged")
    monkeypatch.setenv("PAGERDUTY_API_TOKEN", "env-token")
    monkeypatch.setenv("PAGERDUTY_FROM_EMAIL", "env@example.com")

    publisher = PagerDutyIncidentStatusUpdatePublisher.from_env()

    assert publisher.incident_id == "PENV1"
    assert publisher.status == "acknowledged"
    assert publisher.api_token == "env-token"
    assert publisher.from_email == "env@example.com"


def test_validates_allowed_statuses_before_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid status should not make network calls")

    publisher = PagerDutyIncidentStatusUpdatePublisher(
        incident_id="PINC1",
        status="closed",
        api_token="pd-token",
        from_email="max@example.com",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(PagerDutyIncidentStatusUpdatePublishError, match="must be one of"):
        publisher.publish(dry_run=False)


def test_live_publish_requires_auth() -> None:
    publisher = PagerDutyIncidentStatusUpdatePublisher(incident_id="PINC1", status="resolved")

    with pytest.raises(PagerDutyIncidentStatusUpdatePublishError, match="PAGERDUTY_API_TOKEN"):
        publisher.publish(dry_run=False)
