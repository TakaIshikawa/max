"""Tests for ServiceNow incident publishing."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from max.publisher import ServiceNowIncidentPublisher as ExportedServiceNowIncidentPublisher
from max.publisher.servicenow_incidents import (
    ServiceNowIncidentPublishError,
    ServiceNowIncidentPublisher,
)


def _design_brief_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "design_brief",
            "design_brief_id": "dbf-servicenow001",
            "idea_id": "bu-servicenow001",
            "status": "approved",
            "domain": "it-operations",
            "category": "incident-management",
            "url": "https://max.example.test/design-briefs/dbf-servicenow001",
            "created_at": "2026-04-22T00:00:00+00:00",
            "updated_at": "2026-04-22T00:00:00+00:00",
        },
        "project": {
            "title": "ServiceNow Incident Publisher",
            "summary": "Create operational intake incidents from generated specs.",
            "target_users": "enterprise IT teams",
        },
        "problem": {"statement": "Generated operational handoffs do not reach ITSM queues."},
        "solution": {"approach": "Create ServiceNow incidents through the Table API."},
        "execution": {
            "mvp_scope": ["Incident payload builder", "Live publisher"],
            "validation_plan": "Publish one approved design brief into a ServiceNow sandbox.",
        },
        "evidence": {
            "rationale": "Enterprise teams operationalize delivery through ITSM intake.",
            "insight_ids": ["ins-servicenow001"],
            "signal_ids": ["sig-servicenow001"],
            "source_idea_ids": ["bu-source001"],
        },
        "quality": {
            "quality_score": 8.0,
            "novelty_score": 7.0,
            "usefulness_score": 9.0,
            "rejection_tags": ["handoff_risk"],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
        },
    }


def _design_brief_packet() -> dict:
    return {
        "schema_version": "max.blueprint.source_brief.v1",
        "design_brief": {
            "id": "dbf-servicenow-brief",
            "title": "ServiceNow Operational Intake",
            "domain": "it-operations",
            "theme": "incident-management",
            "lead_idea_id": "bu-lead",
            "source_idea_ids": ["bu-lead", "bu-supporting", "bu-lead"],
            "readiness_score": 91.5,
            "design_status": "ready",
            "merged_product_concept": "Publish validated design briefs into ServiceNow.",
            "validation_plan": "Create one sandbox incident.",
        },
        "source_ideas": [
            {
                "id": "bu-lead",
                "role": "lead",
                "problem": "ITSM intake loses design brief context.",
                "solution": "Map persisted briefs into ServiceNow incidents.",
            }
        ],
    }


def test_dry_run_returns_exact_incident_payload_without_network_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("dry run should not make network calls")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ServiceNowIncidentPublisher(
        instance_url="acme.service-now.com",
        bearer_token="servicenow_token",
        impact="2",
        urgency="2",
        category="software",
        subcategory="application",
        assignment_group="Platform Ops",
        caller_id="max.integration",
        cmdb_ci="Max",
        client=client,
    )

    expected = publisher.build_incident_payload(_design_brief_tact_spec()).to_dict()
    result = publisher.publish(_design_brief_tact_spec(), dry_run=True)

    assert result.payload == expected
    assert result.dry_run is True
    assert result.status_code is None
    assert result.sys_id is None
    assert result.number is None
    assert result.incident_url is None
    assert result.payload["short_description"] == "[Max] ServiceNow Incident Publisher"
    assert result.payload["impact"] == "2"
    assert result.payload["urgency"] == "2"
    assert result.payload["category"] == "software"
    assert result.payload["subcategory"] == "application"
    assert result.payload["assignment_group"] == "Platform Ops"
    assert result.payload["caller_id"] == "max.integration"
    assert result.payload["cmdb_ci"] == "Max"
    assert result.payload["metadata"]["publisher"] == "max.servicenow_incidents"
    assert result.payload["metadata"]["source_type"] == "design_brief"
    assert result.payload["metadata"]["source_id"] == "dbf-servicenow001"
    assert "Publish one approved design brief" in result.payload["description"]


def test_build_design_brief_payload_maps_persisted_brief_fields() -> None:
    publisher = ServiceNowIncidentPublisher(category="request")

    payload = publisher.build_design_brief_payload(
        _design_brief_packet(),
        markdown="# ServiceNow Operational Intake",
    ).to_dict()

    assert payload["short_description"] == "[Max] ServiceNow Operational Intake"
    assert payload["category"] == "request"
    assert payload["metadata"]["source_type"] == "design_brief"
    assert payload["metadata"]["design_brief_id"] == "dbf-servicenow-brief"
    assert payload["metadata"]["source_idea_ids"] == ["bu-lead", "bu-supporting"]
    assert "ITSM intake loses design brief context." in payload["description"]
    assert "Map persisted briefs into ServiceNow incidents." in payload["description"]
    assert "# ServiceNow Operational Intake" in payload["description"]


def test_live_publish_posts_incident_with_bearer_token_and_returns_identifiers() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            201,
            json={
                "result": {
                    "sys_id": "sys-123",
                    "number": "INC0010001",
                    "link": "https://acme.service-now.com/api/now/table/incident/sys-123",
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ServiceNowIncidentPublisher(
        instance_url="https://acme.service-now.com/api/now/table/incident",
        bearer_token="servicenow_token",
        assignment_group="Platform Ops",
        client=client,
    )

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert result.status_code == 201
    assert result.sys_id == "sys-123"
    assert result.number == "INC0010001"
    assert result.incident_url == "https://acme.service-now.com/api/now/table/incident/sys-123"
    assert requests[0].url == "https://acme.service-now.com/api/now/table/incident"
    assert requests[0].headers["Authorization"] == "Bearer servicenow_token"
    assert requests[0].headers["User-Agent"] == "max-servicenow-incidents-publisher/1"
    posted = _json_from_request(requests[0])
    assert posted["short_description"] == "[Max] ServiceNow Incident Publisher"
    assert posted["assignment_group"] == "Platform Ops"
    assert "metadata" not in posted
    assert result.payload["metadata"]["servicenow_incident_sys_id"] == "sys-123"
    assert result.payload["metadata"]["servicenow_incident_number"] == "INC0010001"


def test_live_publish_supports_basic_auth_and_builds_url_when_link_missing() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"result": {"sys_id": "sys-456", "number": "INC0010002"}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = ServiceNowIncidentPublisher(
        instance_url="acme.service-now.com",
        username="agent",
        password="secret",
        client=client,
    )

    result = publisher.publish(_design_brief_tact_spec(), dry_run=False)

    expected_auth = base64.b64encode(b"agent:secret").decode("ascii")
    assert requests[0].headers["Authorization"] == f"Basic {expected_auth}"
    assert result.incident_url == (
        "https://acme.service-now.com/nav_to.do?uri=incident.do?sysparm_query=number=INC0010002"
    )


def test_from_env_reads_servicenow_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SERVICENOW_INSTANCE_URL", "env.service-now.com")
    monkeypatch.setenv("SERVICENOW_USERNAME", "env-user")
    monkeypatch.setenv("SERVICENOW_PASSWORD", "env-password")
    monkeypatch.setenv("SERVICENOW_BEARER_TOKEN", "env-token")
    monkeypatch.setenv("SERVICENOW_INCIDENT_IMPACT", "1")
    monkeypatch.setenv("SERVICENOW_INCIDENT_URGENCY", "2")
    monkeypatch.setenv("SERVICENOW_INCIDENT_CATEGORY", "hardware")
    monkeypatch.setenv("SERVICENOW_INCIDENT_SUBCATEGORY", "laptop")
    monkeypatch.setenv("SERVICENOW_INCIDENT_CONTACT_TYPE", "self-service")
    monkeypatch.setenv("SERVICENOW_ASSIGNMENT_GROUP", "Env Ops")
    monkeypatch.setenv("SERVICENOW_CALLER_ID", "env-caller")
    monkeypatch.setenv("SERVICENOW_CMDB_CI", "env-ci")

    publisher = ServiceNowIncidentPublisher.from_env()

    assert publisher.instance_url == "https://env.service-now.com"
    assert publisher.username == "env-user"
    assert publisher.password == "env-password"
    assert publisher.bearer_token == "env-token"
    assert publisher.impact == "1"
    assert publisher.urgency == "2"
    assert publisher.category == "hardware"
    assert publisher.subcategory == "laptop"
    assert publisher.contact_type == "self-service"
    assert publisher.assignment_group == "Env Ops"
    assert publisher.caller_id == "env-caller"
    assert publisher.cmdb_ci == "env-ci"


def test_live_publish_requires_instance_and_credentials() -> None:
    publisher = ServiceNowIncidentPublisher()

    with pytest.raises(ServiceNowIncidentPublishError, match="SERVICENOW_INSTANCE_URL"):
        publisher.publish(_design_brief_tact_spec(), dry_run=False)

    publisher = ServiceNowIncidentPublisher(instance_url="acme.service-now.com")

    with pytest.raises(ServiceNowIncidentPublishError, match="SERVICENOW_BEARER_TOKEN"):
        publisher.publish(_design_brief_tact_spec(), dry_run=False)


def test_provider_failures_and_malformed_responses_raise_actionable_errors() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                403,
                text=(
                    "bad password=secret "
                    "https://acme.service-now.com/api/now/table/incident?token=url_secret"
                ),
            )
        )
    )
    publisher = ServiceNowIncidentPublisher(
        instance_url="acme.service-now.com",
        username="agent",
        password="secret",
        client=client,
    )

    with pytest.raises(ServiceNowIncidentPublishError, match="HTTP 403") as exc:
        publisher.publish(_design_brief_tact_spec(), dry_run=False)

    assert exc.value.status_code == 403
    assert "secret" not in str(exc.value)
    assert "url_secret" not in str(exc.value)
    assert "token=%3Credacted%3E" in str(exc.value)

    malformed_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json={"result": {}}))
    )
    publisher = ServiceNowIncidentPublisher(
        instance_url="acme.service-now.com",
        bearer_token="servicenow_token",
        client=malformed_client,
    )

    with pytest.raises(ServiceNowIncidentPublishError, match="sys_id"):
        publisher.publish(_design_brief_tact_spec(), dry_run=False)


def test_build_incident_payload_validates_input() -> None:
    publisher = ServiceNowIncidentPublisher()

    with pytest.raises(ServiceNowIncidentPublishError, match="schema_version"):
        publisher.build_incident_payload({"project": {"title": "Missing schema"}})

    with pytest.raises(ServiceNowIncidentPublishError, match="project.title"):
        publisher.build_incident_payload({"schema_version": "tact-spec-preview/v1"})

    with pytest.raises(ServiceNowIncidentPublishError, match="design_brief.title"):
        publisher.build_design_brief_payload({"design_brief": {}})


def test_exported_from_publisher_package() -> None:
    assert ExportedServiceNowIncidentPublisher is ServiceNowIncidentPublisher


def _json_from_request(request: httpx.Request) -> dict:
    return json.loads(request.read())
