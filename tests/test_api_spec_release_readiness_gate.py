"""API tests for TactSpec release readiness gate export."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.release_readiness_gate import RELEASE_READINESS_GATE_SCHEMA_VERSION


def test_post_spec_release_readiness_gate_returns_structured_response() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/spec/release-readiness-gate",
        json={"tact_spec": _complete_tact_spec()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == RELEASE_READINESS_GATE_SCHEMA_VERSION
    assert payload["kind"] == "max.release_readiness_gate"
    assert payload["source"]["idea_id"] == "bu-release-gate-api"
    assert payload["readiness_status"] == "go"
    assert payload["recommendation"] == "yes"
    assert payload["summary"]["decision"] == "go"
    assert payload["summary"]["go"] is True
    assert payload["blockers"] == []
    assert payload["warnings"] == [
        {
            "id": "WRN1",
            "severity": "low",
            "dimension_id": None,
            "message": "No release blockers were detected by the deterministic readiness gate.",
            "recommendation": "Record owner signoffs before publication.",
        }
    ]
    assert payload["recommended_next_actions"] == [
        {
            "id": "NA1",
            "owner": "launch_owner",
            "action": "Record final go/no-go decision with all required owner signoffs.",
            "status": "recommended",
            "blocked_by_dimensions": [],
        }
    ]
    assert [dimension["status"] for dimension in payload["readiness_dimensions"]] == [
        "ready",
        "ready",
        "ready",
        "ready",
        "ready",
        "ready",
        "ready",
    ]


def test_post_spec_release_readiness_gate_accepts_direct_tact_spec_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/release-readiness-gate", json=_complete_tact_spec())

    assert response.status_code == 200
    assert response.json()["source"]["idea_id"] == "bu-release-gate-api"


def test_post_spec_release_readiness_gate_invalid_payload_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/release-readiness-gate", json={"tact_spec": []})

    assert response.status_code == 422
    assert response.json()["detail"]


def _complete_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-release-gate-api",
            "status": "approved",
            "domain": "developer-tools",
            "category": "agent-safety",
        },
        "project": {
            "title": "Release Gate API",
            "summary": "Final release decisioning for generated agent projects.",
            "value_proposition": "Reduce handoff risk before execution agents start work.",
            "target_users": "engineering teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "release approval for generated TactSpec projects",
        },
        "solution": {
            "approach": "Summarize release evidence and required signoffs.",
            "technical_approach": (
                "Python CLI generates a deterministic gate from TactSpec artifacts."
            ),
            "suggested_stack": {
                "language": "python",
                "framework": "fastapi",
                "ci": "github-actions",
            },
        },
        "execution": {
            "mvp_scope": ["Read TactSpec artifacts", "Produce go/no-go decision"],
            "first_10_customers": "three pilot platform teams",
            "validation_plan": "Run the gate against approved and incomplete TactSpec fixtures.",
            "risks": ["Missing artifact evidence may create false release confidence"],
        },
        "evidence": {
            "rationale": "Spec consumers need deterministic final checks.",
            "insight_ids": ["insight-1"],
            "signal_ids": ["signal-1"],
            "source_idea_ids": ["source-1"],
        },
        "evaluation": {
            "overall_score": 86.0,
            "recommendation": "yes",
            "weaknesses": [],
        },
        "acceptance_criteria": {
            "functional_criteria": [
                {"id": "AC-F1", "statement": "Gate returns go for complete evidence."},
                {"id": "AC-F2", "statement": "Gate returns no-go for missing release evidence."},
            ],
            "non_functional_criteria": [
                {"id": "AC-NF1", "statement": "Markdown output is deterministic."}
            ],
        },
        "artifacts": {
            "security_review": {
                "summary": {"finding_count": 1, "high_or_critical_finding_count": 0},
                "findings": [{"id": "SEC-F1", "severity": "low"}],
            },
            "observability_plan": {
                "metrics": [{"id": "MET1", "name": "primary_workflow_success_rate"}],
                "alerts": [{"id": "ALT1", "name": "primary workflow failure"}],
            },
            "rollback_plan": {
                "rollback_triggers": [{"id": "RB1", "name": "primary workflow failure"}],
            },
            "support_playbook": {
                "support_scenarios": [{"id": "SC1", "name": "user cannot complete workflow"}],
            },
            "launch_checklist": {
                "checklist_items": [{"id": "LC1", "task": "run validation"}],
            },
            "stakeholder_handoff": {"summary": {"title": "Release Gate API"}},
        },
    }
