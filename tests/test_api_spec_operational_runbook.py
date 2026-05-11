"""API tests for TactSpec operational runbook generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.operational_runbook import OPERATIONAL_RUNBOOK_SCHEMA_VERSION


def test_post_spec_operational_runbook_returns_runbook_with_markdown() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/operational-runbook", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == OPERATIONAL_RUNBOOK_SCHEMA_VERSION
    assert payload["kind"] == "max.operational_runbook"
    assert payload["source"]["idea_id"] == "bu-runbook-api"
    assert payload["service_overview"]["title"] == "Runbook Console"
    assert payload["health_checks"]
    assert payload["rollback_triggers"]
    assert payload["incident_triage_steps"]
    assert payload["markdown"].startswith("# Runbook Console Operational Runbook")


def test_post_ideas_spec_operational_runbook_accepts_direct_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-operational-runbook", json=_idea())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["service_overview"]["title"] == "Runbook Console"
    assert "## Health Checks" in payload["markdown"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-runbook-api", "status": "approved", "domain": "platform", "category": "application"},
        "project": {
            "title": "Runbook Console",
            "summary": "Operate deployment gates after launch.",
            "target_users": "platform teams",
            "specific_user": "release engineer",
            "buyer": "engineering manager",
            "workflow_context": "CI deployment gate for GitHub and Slack workflows",
        },
        "solution": {
            "technical_approach": "Python service with GitHub checks, Slack escalation, Datadog dashboards, and Postgres storage.",
            "suggested_stack": {"language": "python", "ci": "GitHub", "messaging": "Slack", "observability": "Datadog", "database": "Postgres"},
        },
        "execution": {
            "validation_plan": "Run with three pilot teams using synthetic workflow fixtures.",
            "risks": ["GitHub API outages may block release gates.", "Customer workflow fixtures may include secrets."],
        },
        "evaluation": {"overall_score": 82.0, "recommendation": "yes", "weaknesses": ["Integration reliability must be validated."]},
        "acceptance_criteria": {"functional_criteria": [{"id": "AC-F1", "statement": "GitHub check output is published."}]},
    }


def _idea() -> dict:
    return {
        "title": "Runbook Console",
        "one_liner": "Operate deployment gates after launch.",
        "category": "application",
        "problem": "Release engineers lack generated operating steps.",
        "solution": "Generate an operational runbook from the idea payload.",
        "target_users": "platform teams",
        "value_proposition": "Support and rollback steps are available before launch.",
        "specific_user": "release engineer",
        "buyer": "engineering manager",
        "workflow_context": "CI deployment gate for GitHub and Slack workflows",
        "validation_plan": "Run with three pilot teams using synthetic workflow fixtures.",
        "domain_risks": ["GitHub API outages may block release gates.", "Customer workflow fixtures may include secrets."],
        "tech_approach": "Python service with GitHub checks, Slack escalation, Datadog dashboards, and Postgres storage.",
        "suggested_stack": {"language": "python", "ci": "GitHub", "messaging": "Slack", "observability": "Datadog", "database": "Postgres"},
    }
