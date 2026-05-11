"""API tests for TactSpec observability plan generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.observability_plan import OBSERVABILITY_PLAN_SCHEMA_VERSION


def test_post_spec_observability_plan_returns_plan_sections_and_markdown() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/observability-plan", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == OBSERVABILITY_PLAN_SCHEMA_VERSION
    assert payload["kind"] == "max.observability_plan"
    assert payload["source"]["idea_id"] == "bu-observability-api"
    assert payload["summary"]["title"] == "Observability Console"
    assert payload["metrics"]
    assert payload["alerts"]
    assert payload["dashboards"]
    assert payload["markdown"].startswith("# Observability Console Observability Plan")


def test_post_spec_observability_plan_accepts_direct_spec_and_idea_payloads() -> None:
    client = TestClient(create_app())

    spec_response = client.post("/api/v1/spec/observability-plan", json=_tact_spec())
    idea_response = client.post("/api/v1/ideas/spec-observability-plan", json=_idea())

    assert spec_response.status_code == 200
    assert idea_response.status_code == 200
    assert spec_response.json()["source"]["idea_id"] == "bu-observability-api"
    assert idea_response.json()["summary"]["title"] == "Observability Console"


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-observability-api", "status": "approved", "domain": "platform", "category": "application"},
        "project": {
            "title": "Observability Console",
            "summary": "Observe CI deployment gates and integration health.",
            "target_users": "platform teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "CI deployment gate with GitHub and Slack integrations",
        },
        "solution": {
            "technical_approach": "Python FastAPI service with GitHub checks, Slack notifications, Datadog dashboards, traces, logs, and alerts.",
            "suggested_stack": {"backend": "FastAPI", "ci": "GitHub", "messaging": "Slack", "observability": "Datadog"},
        },
        "execution": {
            "validation_plan": "Run synthetic workflow fixtures against GitHub and Datadog.",
            "risks": ["GitHub API outages may block release gates.", "Datadog alert latency may delay rollback."],
        },
        "acceptance_criteria": {
            "functional_criteria": [{"id": "AC-F1", "statement": "GitHub check output is published."}],
            "non_functional_criteria": [{"id": "AC-NF1", "statement": "Failures emit alerts."}],
        },
        "evaluation": {"overall_score": 82.0, "recommendation": "yes"},
        "evidence": {"signal_ids": ["sig-ci", "sig-alerts"]},
    }


def _idea() -> dict:
    return {
        "title": "Observability Console",
        "one_liner": "Observe CI deployment gates and integration health.",
        "category": "application",
        "problem": "Teams cannot see release gate failures across integrations.",
        "solution": "Generate observability guidance from a TactSpec preview.",
        "target_users": "platform teams",
        "value_proposition": "Operators get metrics and alerts before launch.",
        "specific_user": "platform engineer",
        "buyer": "engineering manager",
        "workflow_context": "CI deployment gate with GitHub and Slack integrations",
        "validation_plan": "Run synthetic workflow fixtures against GitHub and Datadog.",
        "domain_risks": ["GitHub API outages may block release gates.", "Datadog alert latency may delay rollback."],
        "tech_approach": "Python FastAPI service with GitHub checks, Slack notifications, Datadog dashboards, traces, logs, and alerts.",
        "suggested_stack": {"backend": "FastAPI", "ci": "GitHub", "messaging": "Slack", "observability": "Datadog"},
    }
