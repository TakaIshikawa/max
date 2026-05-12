from __future__ import annotations

import json

import httpx
import pytest

from max.publisher.statuspage_incidents import StatuspageIncidentPublishError, StatuspageIncidentPublisher


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"system": "max", "type": "idea", "idea_id": "bu-sp-create001"},
        "project": {"title": "Statuspage Incident Publisher", "summary": "Create customer-facing incidents."},
        "execution": {"validation_plan": "Create a sandbox incident."},
    }


def test_dry_run_builds_statuspage_incident_payload() -> None:
    publisher = StatuspageIncidentPublisher(
        page_id="page123",
        status="identified",
        impact="major",
        body="Incident body",
        component_ids=["component-1"],
        components={"component-1": "degraded_performance"},
        scheduled_for="2026-05-13T10:00:00Z",
        scheduled_until="2026-05-13T11:00:00Z",
    )

    result = publisher.publish(_tact_spec(), dry_run=True)

    assert result.endpoint == "https://api.statuspage.io/v1/pages/page123/incidents"
    assert result.incident_id is None
    assert result.payload["name"] == "Statuspage Incident Publisher"
    assert result.payload["status"] == "identified"
    assert result.payload["impact"] == "major"
    assert result.payload["body"] == "Incident body"
    assert result.payload["component_ids"] == ["component-1"]
    assert result.payload["components"] == {"component-1": "degraded_performance"}
    assert result.payload["scheduled_for"] == "2026-05-13T10:00:00Z"
    assert result.payload["metadata"]["publisher"] == "max.statuspage_incidents"


def test_live_publish_posts_incident_and_returns_metadata() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"incident": {"id": "inc123", "shortlink": "https://stspg.io/abc"}})

    publisher = StatuspageIncidentPublisher(
        page_id="page123",
        api_key="sp-secret",
        api_url="https://statuspage.example.test",
        body="Incident body",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.incident_id == "inc123"
    assert result.incident_url == "https://stspg.io/abc"
    assert requests[0].url == "https://statuspage.example.test/v1/pages/page123/incidents"
    assert requests[0].headers["Authorization"] == "OAuth sp-secret"
    assert json.loads(requests[0].read())["incident"]["body"] == "Incident body"


def test_from_env_reads_statuspage_incident_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STATUSPAGE_API_KEY", "env-key")
    monkeypatch.setenv("STATUSPAGE_PAGE_ID", "page-env")
    monkeypatch.setenv("STATUSPAGE_INCIDENT_STATUS", "monitoring")
    monkeypatch.setenv("STATUSPAGE_INCIDENT_IMPACT", "critical")

    publisher = StatuspageIncidentPublisher.from_env()

    assert publisher.api_key == "env-key"
    assert publisher.page_id == "page-env"
    assert publisher.status == "monitoring"
    assert publisher.impact == "critical"


def test_live_publish_requires_api_key() -> None:
    publisher = StatuspageIncidentPublisher(page_id="page123")

    with pytest.raises(StatuspageIncidentPublishError, match="STATUSPAGE_API_KEY"):
        publisher.publish(_tact_spec(), dry_run=False)
