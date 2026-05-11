"""API tests for TactSpec data retention schedule generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.data_retention_schedule import DATA_RETENTION_SCHEDULE_SCHEMA_VERSION


def test_post_spec_data_retention_schedule_returns_schedule_with_markdown() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/data-retention-schedule", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == DATA_RETENTION_SCHEDULE_SCHEMA_VERSION
    assert payload["kind"] == "max.spec.data_retention_schedule"
    assert payload["idea_id"] == "bu-retention-api"
    assert payload["source"]["idea_id"] == "bu-retention-api"
    assert payload["summary"]["title"] == "Retention Console"
    assert payload["retention_rules"]
    assert payload["deletion_triggers"]
    assert payload["markdown"].startswith("# Retention Console Data Retention Schedule")


def test_post_spec_data_retention_schedule_accepts_direct_spec_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/data-retention-schedule", json=_tact_spec())

    assert response.status_code == 200
    assert response.json()["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"


def test_post_ideas_spec_data_retention_schedule_accepts_direct_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-data-retention-schedule", json=_idea())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["summary"]["title"] == "Retention Console"
    assert "## Retention Rules" in payload["markdown"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {"idea_id": "bu-retention-api", "status": "approved", "domain": "platform", "category": "application"},
        "project": {
            "title": "Retention Console",
            "summary": "Manage retention for customer records and exports.",
            "target_users": "operations teams",
            "specific_user": "operations analyst",
            "buyer": "operations lead",
            "workflow_context": "customer workflow exports and audit log review",
        },
        "problem": {"statement": "Teams keep CSV exports and customer records too long."},
        "solution": {
            "technical_approach": "Postgres stores customer records, audit logs, OpenAI prompts, CSV exports, OAuth tokens, and Slack webhook payloads.",
            "suggested_stack": {"database": "Postgres", "messaging": "Slack", "ai": "OpenAI"},
        },
        "execution": {
            "validation_plan": "Review deletion triggers with data owners.",
            "risks": ["Exports can include customer identifiers."],
            "mvp_scope": ["Retain logs for 30 days", "Expire exports after 14 days"],
        },
        "evidence": {"rationale": "Customer export workflows need retention controls.", "signal_ids": ["sig-retention"]},
    }


def _idea() -> dict:
    return {
        "title": "Retention Console",
        "one_liner": "Manage retention for customer records and exports.",
        "category": "application",
        "problem": "Teams keep CSV exports and customer records too long.",
        "solution": "Generate retention guidance for submitted ideas.",
        "target_users": "operations teams",
        "value_proposition": "Data owners get retention rules before launch.",
        "specific_user": "operations analyst",
        "buyer": "operations lead",
        "workflow_context": "customer workflow exports and audit log review",
        "validation_plan": "Review deletion triggers with data owners.",
        "domain_risks": ["Exports can include customer identifiers."],
        "evidence_rationale": "Customer export workflows need retention controls.",
        "tech_approach": "Postgres stores customer records, audit logs, OpenAI prompts, CSV exports, OAuth tokens, and Slack webhook payloads.",
        "suggested_stack": {"database": "Postgres", "messaging": "Slack", "ai": "OpenAI"},
    }
