"""API tests for TactSpec disaster recovery plan generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.disaster_recovery_plan import DISASTER_RECOVERY_PLAN_SCHEMA_VERSION


def test_post_spec_disaster_recovery_plan_returns_plan_with_markdown() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/disaster-recovery-plan", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == DISASTER_RECOVERY_PLAN_SCHEMA_VERSION
    assert payload["kind"] == "max.disaster_recovery_plan"
    assert payload["source"]["idea_id"] == "bu-dr-api"
    assert payload["summary"]["title"] == "Disaster Recovery Console"
    assert payload["recovery_objectives"]
    assert payload["backup_strategy"]
    assert payload["failover_steps"]
    assert payload["markdown"].startswith("# Disaster Recovery Console Disaster Recovery Plan")


def test_post_ideas_spec_disaster_recovery_plan_accepts_direct_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-disaster-recovery-plan", json=_idea())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["summary"]["title"] == "Disaster Recovery Console"
    assert "## Failover Steps" in payload["markdown"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-dr-api", "status": "approved", "domain": "customer-success", "category": "application"},
        "project": {
            "title": "Disaster Recovery Console",
            "summary": "Recover customer success workflows across integrations.",
            "target_users": "customer success teams",
            "specific_user": "customer success operator",
            "buyer": "customer success director",
            "workflow_context": "Salesforce account review to Slack renewal alert",
        },
        "solution": {
            "technical_approach": "FastAPI service with OAuth, Slack notifications, Salesforce sync, Postgres storage, Redis queues, and Datadog dashboards.",
            "suggested_stack": {"backend": "FastAPI", "database": "Postgres", "messaging": "Slack", "queue": "Redis", "observability": "Datadog"},
        },
        "execution": {
            "validation_plan": "Run Salesforce sandbox sync and Slack alert fixture.",
            "risks": ["Salesforce outage may delay customer renewal workflows.", "Customer data restore must preserve audit records."],
        },
        "evaluation": {"overall_score": 84, "weaknesses": ["Integration reliability must be proven."]},
        "evidence": {"signal_ids": ["sig-cs-workflow"]},
    }


def _idea() -> dict:
    return {
        "title": "Disaster Recovery Console",
        "one_liner": "Recover customer success workflows across integrations.",
        "category": "application",
        "problem": "Customer workflows depend on Salesforce, Slack, and Postgres recovery.",
        "solution": "Generate a disaster recovery plan from the submitted idea.",
        "target_users": "customer success teams",
        "value_proposition": "Operators get recovery objectives before launch.",
        "specific_user": "customer success operator",
        "buyer": "customer success director",
        "workflow_context": "Salesforce account review to Slack renewal alert",
        "validation_plan": "Run Salesforce sandbox sync and Slack alert fixture.",
        "domain_risks": ["Salesforce outage may delay customer renewal workflows.", "Customer data restore must preserve audit records."],
        "tech_approach": "FastAPI service with OAuth, Slack notifications, Salesforce sync, Postgres storage, Redis queues, and Datadog dashboards.",
        "suggested_stack": {"backend": "FastAPI", "database": "Postgres", "messaging": "Slack", "queue": "Redis", "observability": "Datadog"},
    }
