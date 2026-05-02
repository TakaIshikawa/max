"""API tests for TactSpec cost estimate generation."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.cost_estimate import COST_ESTIMATE_SCHEMA_VERSION


def test_post_spec_cost_estimate_returns_structured_data_and_markdown_from_spec() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/cost-estimate", json={"tact_spec": _tact_spec_payload()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == COST_ESTIMATE_SCHEMA_VERSION
    assert payload["kind"] == "max.cost_estimate"
    assert payload["source"]["idea_id"] == "bu-cost-api001"
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "Cost Estimate API"
    assert payload["summary"]["effort_band"] in {"medium", "high"}
    assert payload["effort_estimate"]["engineering_days"]
    assert {driver["category"] for driver in payload["cost_drivers"]} >= {
        "external_service",
        "operational",
    }
    assert payload["risks"]
    assert payload["recommendations"]
    assert payload["markdown"].startswith("# Cost Estimate API Cost Estimate")
    assert "## Effort Estimate" in payload["markdown"]
    assert "## Cost Drivers" in payload["markdown"]
    assert "## Recommendations" in payload["markdown"]


def test_post_spec_cost_estimate_accepts_direct_spec_payload() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/cost-estimate", json=_tact_spec_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["idea_id"] == "bu-cost-api001"
    assert payload["markdown"].startswith("# Cost Estimate API Cost Estimate")


def test_post_spec_cost_estimate_returns_structured_data_and_markdown_from_idea() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/ideas/spec-cost-estimate", json={"idea": _idea_payload()})

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == COST_ESTIMATE_SCHEMA_VERSION
    assert payload["kind"] == "max.cost_estimate"
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "Cost Estimate API"
    assert payload["summary"]["stack"] == (
        "backend=FastAPI, database=Postgres, messaging=Slack, provider=OpenAI"
    )
    assert payload["markdown"].startswith("# Cost Estimate API Cost Estimate")
    assert "Slack" in payload["markdown"]


def test_post_spec_cost_estimate_invalid_payload_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/cost-estimate", json={"idea": {"title": "Incomplete"}})

    assert response.status_code == 422
    assert response.json()["detail"]


def test_post_spec_cost_estimate_empty_tact_spec_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/cost-estimate", json={"tact_spec": {}})

    assert response.status_code == 422
    assert response.json()["detail"]


def _idea_payload() -> dict:
    return {
        "title": "Cost Estimate API",
        "one_liner": "Expose generated cost estimates to budgeting clients",
        "category": "application",
        "problem": (
            "Automation teams cannot budget OpenAI, Slack, and Postgres projects from a "
            "small API request."
        ),
        "solution": "Generate a deterministic cost estimate from a TactSpec preview.",
        "target_users": "platform automation teams",
        "value_proposition": "Project selection workflows can compare cost drivers directly.",
        "specific_user": "portfolio automation owner",
        "buyer": "platform operations lead",
        "workflow_context": "budget review before build approval",
        "current_workaround": "Teams inspect generated specs and manually list service costs.",
        "why_now": "More project selection is moving into automated review gates.",
        "validation_plan": "Call the REST endpoint and verify JSON plus Markdown output.",
        "first_10_customers": "internal platform and finance teams",
        "domain_risks": [
            "OpenAI usage can increase with pilot traffic.",
            "Slack integration support may require on-call ownership.",
        ],
        "evidence_rationale": "Existing cost estimate generation already computes the artifact.",
        "tech_approach": (
            "FastAPI endpoint backed by Postgres, Slack webhooks, and OpenAI model calls."
        ),
        "suggested_stack": {
            "backend": "FastAPI",
            "database": "Postgres",
            "messaging": "Slack",
            "provider": "OpenAI",
        },
        "composability_notes": "Generated from payloads without extra persistence.",
    }


def _tact_spec_payload() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-cost-api001",
            "status": "pending",
            "domain": "platform",
            "category": "application",
        },
        "project": {
            "title": "Cost Estimate API",
            "summary": "Expose generated cost estimates to budgeting clients",
            "target_users": "platform automation teams",
            "specific_user": "portfolio automation owner",
            "buyer": "platform operations lead",
            "workflow_context": "budget review before build approval",
        },
        "solution": {
            "approach": "Generate a deterministic cost estimate from a TactSpec preview.",
            "technical_approach": (
                "FastAPI endpoint backed by OpenAI model calls, Slack webhooks, and Postgres."
            ),
            "suggested_stack": {
                "backend": "FastAPI",
                "database": "Postgres",
                "messaging": "Slack",
                "provider": "OpenAI",
            },
        },
        "execution": {
            "mvp_scope": [
                "Accept spec payloads",
                "Accept idea payloads",
                "Return markdown for budget review",
            ],
            "first_10_customers": "internal platform and finance teams",
            "validation_plan": "Run API tests and compare generated Markdown.",
            "risks": ["OpenAI usage can increase with pilot traffic."],
        },
        "quality": {"quality_score": 0.82, "rejection_tags": []},
        "evaluation": {
            "overall_score": 84.0,
            "recommendation": "yes",
            "weaknesses": ["Pilot usage may need budget guardrails."],
            "dimensions": {"build_effort": {"value": 8.0, "confidence": 0.8}},
        },
    }
