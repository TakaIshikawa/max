"""API tests for TactSpec smoke test plan export."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.smoke_test_plan import SMOKE_TEST_PLAN_SCHEMA_VERSION


def test_post_spec_smoke_test_plan_returns_structured_response() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/spec/smoke-test-plan",
        json={"tact_spec": _complete_tact_spec()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SMOKE_TEST_PLAN_SCHEMA_VERSION
    assert payload["kind"] == "max.smoke_test_plan"
    assert payload["source"]["idea_id"] == "bu-smoke-test-plan-api"
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"] == {
        "title": "Smoke Test Plan API",
        "target_user": "platform engineer",
        "buyer": "engineering manager",
        "workflow_context": "post-generation release verification",
        "stack": "ci=github-actions, framework=fastapi, language=python",
        "validation_plan": "Run smoke checks against approved TactSpec fixtures.",
        "recommendation": "yes",
        "overall_score": 84.0,
    }
    assert [check["id"] for check in payload["user_journey_checks"]] == [
        "UJ1",
        "UJ2",
        "UJ3",
        "UJ4",
    ]
    assert payload["deployment_verification_checks"][0]["owner"] == "release_owner"
    assert payload["integration_checks"][0]["category"] == "integration"
    assert payload["data_integrity_checks"][0]["category"] == "data_integrity"
    assert payload["observability_checks"][0]["category"] == "observability"
    assert payload["rollback_verification_checks"][0]["category"] == "rollback"
    assert [owner["id"] for owner in payload["owners"]] == [
        "OWN1",
        "OWN2",
        "OWN3",
        "OWN4",
        "OWN5",
        "OWN6",
    ]
    assert [reference["id"] for reference in payload["evidence_references"]] == [
        "insight:insight-smoke",
        "signal:signal-smoke",
        "spec:evidence_rationale",
    ]


def test_post_spec_smoke_test_plan_accepts_direct_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/smoke-test-plan", json=_idea_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "idea"
    assert payload["source"]["tact_spec_kind"] == "tact.project_spec"
    assert payload["summary"]["title"] == "Direct Idea Smoke Plan"
    assert payload["summary"]["workflow_context"] == "release approval automation"
    assert payload["summary"]["stack"] == "framework=fastapi, language=python"


def test_post_spec_smoke_test_plan_invalid_payload_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/smoke-test-plan", json={"tact_spec": []})

    assert response.status_code == 422
    assert response.json()["detail"]


def _complete_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-smoke-test-plan-api",
            "status": "approved",
            "domain": "developer-tools",
            "category": "agent-safety",
        },
        "project": {
            "title": "Smoke Test Plan API",
            "summary": "Expose smoke test plans to automation clients.",
            "value_proposition": "Reduce release handoff risk after spec generation.",
            "target_users": "engineering teams",
            "specific_user": "platform engineer",
            "buyer": "engineering manager",
            "workflow_context": "post-generation release verification",
        },
        "solution": {
            "approach": "Return deterministic smoke checks for a supplied TactSpec.",
            "technical_approach": "FastAPI endpoint calls the smoke test plan generator.",
            "suggested_stack": {
                "language": "python",
                "framework": "fastapi",
                "ci": "github-actions",
            },
            "composability_notes": "Automation clients can attach checks to release jobs.",
        },
        "execution": {
            "mvp_scope": ["Generate structured plan", "Expose REST response"],
            "first_10_customers": "three pilot platform teams",
            "validation_plan": "Run smoke checks against approved TactSpec fixtures.",
            "risks": ["Missing runtime evidence may delay release approval"],
        },
        "evidence": {
            "rationale": "Spec consumers need immediate post-generation verification.",
            "insight_ids": ["insight-smoke"],
            "signal_ids": ["signal-smoke"],
            "source_idea_ids": [],
        },
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
            "weaknesses": [],
        },
    }


def _idea_payload() -> dict:
    return {
        "title": "Direct Idea Smoke Plan",
        "one_liner": "Generate smoke plans directly from idea payloads.",
        "category": "developer-tools",
        "problem": "Automation clients cannot request smoke plans before persisting ideas.",
        "solution": "Build a TactSpec preview from the submitted idea payload.",
        "target_users": "engineering teams",
        "value_proposition": "Make release smoke checks available earlier in the workflow.",
        "specific_user": "release engineer",
        "buyer": "engineering manager",
        "workflow_context": "release approval automation",
        "validation_plan": "Run the API against fixture idea payloads.",
        "tech_approach": "FastAPI endpoint delegates to the existing generator.",
        "suggested_stack": {"language": "python", "framework": "fastapi"},
        "domain_risks": ["Sparse ideas may produce generic checks"],
        "evidence_rationale": "Release engineers asked for automation-friendly smoke plans.",
    }
