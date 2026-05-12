from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from max.publisher.opsgenie_incidents import OpsgenieIncidentPublishError, OpsgenieIncidentPublisher
from tests.test_slack_scheduled_message_publisher import _tact_spec


def test_dry_run_builds_deterministic_incident_payload() -> None:
    publisher = OpsgenieIncidentPublisher(
        api_key="ops-key",
        priority="P2",
        responders=[{"type": "team", "name": "Platform"}],
        tags=["launch"],
        details={"runbook": "https://runbooks.example.test/max"},
        note="Review before launch",
    )

    first = publisher.publish(_tact_spec(), dry_run=True)
    second = publisher.publish(_tact_spec(), dry_run=True)

    assert first.payload == second.payload
    assert first.dry_run is True
    assert first.endpoint == "https://api.opsgenie.com/v1/incidents/create"
    assert first.payload["message"] == "[Max] Slack Scheduled Message Publisher"
    assert first.payload["priority"] == "P2"
    assert first.payload["responders"] == [{"type": "team", "name": "Platform"}]
    assert first.payload["tags"] == ["max", "tact-spec", "publisher:opsgenie", "domain-platform", "category-launch", "launch"]
    assert first.payload["details"]["runbook"] == "https://runbooks.example.test/max"
    assert first.payload["details"]["max_metadata"]["publisher"] == "max.opsgenie_incidents"
    assert first.payload["note"] == "Review before launch"


def test_live_publish_posts_incident_with_geniekey_auth() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"requestId": "req-123", "result": "Request will be processed"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = OpsgenieIncidentPublisher(
        api_key="ops-key",
        api_url="https://api.eu.opsgenie.com/v1/incidents/create",
        message="Custom incident",
        description="Custom description",
        priority="P1",
        responders=["Platform"],
        details={"owner": "SRE"},
        client=client,
    )

    result = publisher.publish(_tact_spec(), dry_run=False)

    assert result.status_code == 202
    assert result.request_id == "req-123"
    assert result.result == "Request will be processed"
    assert requests[0].url == "https://api.eu.opsgenie.com/v1/incidents/create"
    assert requests[0].headers["Authorization"] == "GenieKey ops-key"
    posted = json.loads(requests[0].read())
    assert posted["message"] == "Custom incident"
    assert posted["description"] == "Custom description"
    assert posted["priority"] == "P1"
    assert posted["responders"] == [{"type": "team", "name": "Platform"}]
    assert posted["details"]["owner"] == "SRE"
    assert isinstance(posted["details"]["max_metadata"], str)


def test_from_env_reads_opsgenie_incident_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPSGENIE_API_KEY", "env-key")
    monkeypatch.setenv("OPSGENIE_API_URL", "api.eu.opsgenie.com")
    monkeypatch.setenv("OPSGENIE_INCIDENT_MESSAGE", "Env incident")
    monkeypatch.setenv("OPSGENIE_INCIDENT_DESCRIPTION", "Env description")
    monkeypatch.setenv("OPSGENIE_INCIDENT_PRIORITY", "p4")
    monkeypatch.setenv("OPSGENIE_INCIDENT_RESPONDERS", "Primary, Backup")
    monkeypatch.setenv("OPSGENIE_INCIDENT_TAGS", "env-one, env-two")
    monkeypatch.setenv("OPSGENIE_INCIDENT_NOTE", "Env note")

    publisher = OpsgenieIncidentPublisher.from_env()

    assert publisher.api_key == "env-key"
    assert publisher.endpoint == "https://api.eu.opsgenie.com/v1/incidents/create"
    assert publisher.message == "Env incident"
    assert publisher.description == "Env description"
    assert publisher.priority == "P4"
    assert publisher.responders == [{"type": "team", "name": "Primary"}, {"type": "team", "name": "Backup"}]
    assert publisher.tags == ["env-one", "env-two"]
    assert publisher.note == "Env note"


def test_validation_http_errors_and_secret_redaction() -> None:
    with pytest.raises(OpsgenieIncidentPublishError, match="OPSGENIE_API_KEY"):
        OpsgenieIncidentPublisher().publish(_tact_spec(), dry_run=False)

    with pytest.raises(OpsgenieIncidentPublishError, match="priority"):
        OpsgenieIncidentPublisher(priority="critical")

    with pytest.raises(OpsgenieIncidentPublishError, match="details"):
        invalid_details: Any = ["not", "a", "dict"]
        OpsgenieIncidentPublisher(details=invalid_details)

    with pytest.raises(OpsgenieIncidentPublishError, match="schema_version"):
        OpsgenieIncidentPublisher().build_incident_payload({"project": {"title": "Missing schema"}})

    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="bad api_key=ops-secret")))
    publisher = OpsgenieIncidentPublisher(api_key="ops-secret", client=client)
    with pytest.raises(OpsgenieIncidentPublishError, match="HTTP 403") as exc:
        publisher.publish(_tact_spec(), dry_run=False)
    assert "ops-secret" not in str(exc.value)
