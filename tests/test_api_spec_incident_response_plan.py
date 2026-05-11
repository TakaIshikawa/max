"""API tests for TactSpec incident response plan generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.incident_response_plan import INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION


def test_post_spec_incident_response_plan_returns_sections_and_markdown() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/incident-response-plan", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
    assert payload["kind"] == "max.incident_response_plan"
    assert payload["source"]["idea_id"] == "bu-incident-api"
    assert payload["summary"]["title"] == "Incident Console"
    assert payload["incident_classes"]
    assert payload["triage_steps"]
    assert payload["containment_actions"]
    assert payload["markdown"].startswith("# Incident Console Incident Response Plan")


def test_post_ideas_spec_incident_response_plan_accepts_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-incident-response-plan", json=_idea())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["summary"]["title"] == "Incident Console"
    assert "## Triage Steps" in payload["markdown"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-incident-api", "status": "approved", "domain": "security", "category": "application"},
        "project": {
            "title": "Incident Console",
            "summary": "Coordinate security incidents for customer webhooks.",
            "target_users": "security teams",
            "specific_user": "security engineer",
            "buyer": "security lead",
            "workflow_context": "OAuth webhook incident triage and customer notification",
        },
        "solution": {
            "technical_approach": "FastAPI webhook API with OAuth, SSO, RBAC roles, audit logs, rate limits, encrypted secrets, Slack escalation, and Datadog alerts.",
            "suggested_stack": {"backend": "FastAPI", "auth": "OAuth", "messaging": "Slack", "observability": "Datadog"},
        },
        "execution": {
            "validation_plan": "Run token leak tabletop and webhook replay drill.",
            "risks": ["OAuth token leak could expose customer data.", "Datadog alert latency may delay rollback."],
        },
        "evaluation": {"weaknesses": ["Security review is required before production data access."]},
        "evidence": {"signal_ids": ["sig-security"]},
    }


def _idea() -> dict:
    return {
        "title": "Incident Console",
        "one_liner": "Coordinate security incidents for customer webhooks.",
        "category": "application",
        "problem": "Teams lack a repeatable incident response plan for webhook failures.",
        "solution": "Generate incident response sections from a TactSpec preview.",
        "target_users": "security teams",
        "value_proposition": "Incident owners can act from generated plans.",
        "specific_user": "security engineer",
        "buyer": "security lead",
        "workflow_context": "OAuth webhook incident triage and customer notification",
        "validation_plan": "Run token leak tabletop and webhook replay drill.",
        "domain_risks": ["OAuth token leak could expose customer data.", "Datadog alert latency may delay rollback."],
        "tech_approach": "FastAPI webhook API with OAuth, SSO, RBAC roles, audit logs, rate limits, encrypted secrets, Slack escalation, and Datadog alerts.",
        "suggested_stack": {"backend": "FastAPI", "auth": "OAuth", "messaging": "Slack", "observability": "Datadog"},
    }
