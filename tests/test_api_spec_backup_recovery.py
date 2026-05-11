"""API tests for TactSpec backup recovery generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.backup_recovery import BACKUP_RECOVERY_SCHEMA_VERSION


def test_post_spec_backup_recovery_returns_structured_response_for_wrapped_spec() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/backup-recovery", json={"tact_spec": _tact_spec()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == BACKUP_RECOVERY_SCHEMA_VERSION
    assert payload["kind"] == "max.backup_recovery_plan"
    assert payload["source"]["idea_id"] == "bu-artifact-api"
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "Artifact API"
    assert payload["summary"]["plan_count"] >= 3
    assert {plan["type"] for plan in payload["backup_plans"]} >= {
        "database",
        "audit_logs",
        "code_deployment",
        "disaster_recovery",
    }


def test_post_spec_backup_recovery_accepts_direct_spec_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/backup-recovery", json=_tact_spec())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["idea_id"] == "bu-artifact-api"
    assert payload["source"]["status"] == "approved"


def test_post_ideas_spec_backup_recovery_accepts_wrapped_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-backup-recovery", json={"idea": _idea()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["source"]["tact_spec_kind"] == "tact.project_spec"
    assert payload["summary"]["title"] == "Artifact API"
    assert any(plan["type"] == "database" for plan in payload["backup_plans"])


def test_post_spec_backup_recovery_accepts_direct_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/backup-recovery", json=_idea())

    assert response.status_code == 200
    assert response.json()["summary"]["title"] == "Artifact API"


def test_post_spec_backup_recovery_invalid_payload_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/backup-recovery", json={"tact_spec": []})

    assert response.status_code == 422
    assert response.json()["detail"]


def test_post_spec_backup_recovery_empty_payload_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/backup-recovery", json={"tact_spec": {}})

    assert response.status_code == 422
    assert response.json()["detail"]


def _tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-artifact-api",
            "status": "approved",
            "domain": "platform",
            "category": "application",
        },
        "project": {
            "title": "Artifact API",
            "summary": "Expose operational artifacts for platform teams.",
            "value_proposition": "Reduce production planning handoff work.",
            "target_users": "platform teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "release planning for customer data workflows",
        },
        "solution": {
            "approach": "Return deterministic operational artifacts from FastAPI.",
            "technical_approach": "FastAPI service with Postgres, Redis cache, S3 files, OAuth secrets, and Slack webhooks.",
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
                "cache": "Redis",
                "storage": "S3",
                "messaging": "Slack",
            },
        },
        "execution": {
            "mvp_scope": ["Generate artifact", "Expose endpoint"],
            "validation_plan": "Call the endpoint with fixture TactSpecs.",
            "risks": ["Customer data restore must preserve audit logs."],
        },
        "evidence": {"rationale": "Operations teams need API access to generated artifacts."},
        "evaluation": {"overall_score": 84.0, "recommendation": "yes"},
    }


def _idea() -> dict:
    return {
        "title": "Artifact API",
        "one_liner": "Expose generated operational artifacts to automation clients.",
        "category": "application",
        "problem": "Teams cannot request recovery planning before persisting ideas.",
        "solution": "Generate a TactSpec preview from an ad hoc idea payload.",
        "target_users": "platform teams",
        "value_proposition": "Operational handoffs are available earlier.",
        "specific_user": "platform engineer",
        "buyer": "engineering manager",
        "workflow_context": "release planning for customer data workflows",
        "validation_plan": "Call the endpoint with fixture idea payloads.",
        "domain_risks": ["Customer data restore must preserve audit logs."],
        "evidence_rationale": "Operations teams need API access to generated artifacts.",
        "tech_approach": "FastAPI service with Postgres, Redis cache, S3 files, OAuth secrets, and Slack webhooks.",
        "suggested_stack": {
            "backend": "FastAPI",
            "database": "Postgres",
            "cache": "Redis",
            "storage": "S3",
            "messaging": "Slack",
        },
    }
