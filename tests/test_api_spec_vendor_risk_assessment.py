"""API tests for TactSpec vendor risk assessment generation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import max.server.api as api
from max.server.app import create_app
from max.spec.vendor_risk_assessment import VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def vendor_risk_db(tmp_path) -> str:
    db_path = str(tmp_path / "vendor_risk_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_vendor_risk_unit())
    finally:
        store.close()
    return db_path


@pytest.fixture
def vendor_risk_client(vendor_risk_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=vendor_risk_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_idea_vendor_risk_assessment_returns_structured_json(
    vendor_risk_client: TestClient,
) -> None:
    response = vendor_risk_client.get(
        "/api/v1/ideas/bu-vendor-risk-api001/vendor-risk-assessment"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION
    assert payload["kind"] == "max.spec.vendor_risk_assessment"
    assert payload["source"]["idea_id"] == "bu-vendor-risk-api001"
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "Vendor Risk API"
    assert payload["vendors"]
    assert payload["risks"]
    assert payload["mitigations"]
    assert payload["gate_decision"]["status"] in {"blocked", "review_required"}
    assert {vendor["name"] for vendor in payload["vendors"]} >= {"OpenAI", "Slack"}
    assert all(risk["severity"] for risk in payload["risks"])
    assert all(risk["likelihood"] for risk in payload["risks"])
    assert any(risk["evidence"] for risk in payload["risks"])


def test_post_spec_vendor_risk_assessment_accepts_wrapped_spec_payload() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/spec/vendor-risk-assessment",
        json={"tact_spec": _tact_spec_payload()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION
    assert payload["source"]["idea_id"] == "bu-vendor-risk-api001"
    assert payload["summary"]["vendor_count"] >= 4
    assert {risk["category"] for risk in payload["risks"]} >= {
        "sensitive_vendor_transfer",
        "critical_vendor_dependency",
    }
    assert all("severity" in risk and "likelihood" in risk for risk in payload["risks"])
    assert any(item["owner"] == "privacy_owner" for item in payload["mitigations"])


def test_post_spec_vendor_risk_assessment_accepts_idea_payload() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/v1/ideas/spec-vendor-risk-assessment",
        json={"idea": _idea_payload()},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "Vendor Risk API"
    assert {vendor["name"] for vendor in payload["vendors"]} >= {"OpenAI", "Slack"}


def test_get_idea_vendor_risk_assessment_missing_idea_returns_not_found_without_generation(
    vendor_risk_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generate_vendor_risk_assessment(*args, **kwargs):
        raise AssertionError("missing ideas must not generate vendor risk assessments")

    monkeypatch.setattr(
        api,
        "generate_vendor_risk_assessment",
        fail_generate_vendor_risk_assessment,
    )

    response = vendor_risk_client.get("/api/v1/ideas/bu-missing/vendor-risk-assessment")

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def test_post_spec_vendor_risk_assessment_empty_tact_spec_returns_validation_error() -> None:
    client = TestClient(create_app())

    response = client.post("/api/v1/spec/vendor-risk-assessment", json={"tact_spec": {}})

    assert response.status_code == 422
    assert response.json()["detail"]


def _vendor_risk_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-vendor-risk-api001",
        title="Vendor Risk API",
        one_liner="Expose vendor risk assessments to compliance dashboards",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Teams send patient data through OpenAI and Slack without a direct review artifact.",
        solution="Generate deterministic vendor risk assessment JSON from each TactSpec preview.",
        target_users="platform compliance reviewers",
        value_proposition="Review dashboards can consume vendor risks without parsing bundles.",
        specific_user="compliance automation owner",
        buyer="platform risk lead",
        workflow_context="pre-release vendor review",
        current_workaround="Teams manually inspect generated specs and list vendor evidence.",
        why_now="More release gates require automated vendor review evidence.",
        validation_plan="Fetch the REST endpoint and verify JSON risk fields.",
        first_10_customers="internal compliance and platform teams",
        domain_risks=[
            "Patient PII must not leak into Slack messages or AI prompts.",
            "Vendor outage requires queue retry and manual fallback.",
        ],
        evidence_rationale="Existing TactSpec generation already computes vendor risk context.",
        tech_approach=(
            "FastAPI service using OpenAI summaries, Slack alerts, Supabase storage, "
            "Datadog logs, queue retry, fallback workflow, DPA, BAA, SLA, and SOC 2 evidence."
        ),
        suggested_stack={
            "backend": "FastAPI",
            "ai": "OpenAI",
            "messaging": "Slack",
            "database": "Supabase",
            "observability": "Datadog",
        },
        composability_notes="Generated on demand from persisted idea data.",
    )


def _idea_payload() -> dict:
    return {
        "title": "Vendor Risk API",
        "one_liner": "Expose vendor risk assessments to compliance dashboards",
        "category": "application",
        "problem": "Teams send patient PII through vendors without a direct review artifact.",
        "solution": "Generate deterministic vendor risk assessment JSON from each TactSpec preview.",
        "target_users": "platform compliance reviewers",
        "value_proposition": "Review dashboards can consume vendor risks without parsing bundles.",
        "specific_user": "compliance automation owner",
        "buyer": "platform risk lead",
        "workflow_context": "pre-release vendor review",
        "current_workaround": "Teams manually inspect generated specs and list vendor evidence.",
        "why_now": "More release gates require automated vendor review evidence.",
        "validation_plan": "Fetch the REST endpoint and verify JSON risk fields.",
        "first_10_customers": "internal compliance and platform teams",
        "domain_risks": [
            "Patient PII must not leak into Slack messages or AI prompts.",
            "Vendor outage requires queue retry and manual fallback.",
        ],
        "evidence_rationale": "Existing TactSpec generation already computes vendor risk context.",
        "tech_approach": (
            "FastAPI service using OpenAI summaries, Slack alerts, Supabase storage, "
            "DPA, BAA, SLA, and SOC 2 evidence."
        ),
        "suggested_stack": {
            "backend": "FastAPI",
            "ai": "OpenAI",
            "messaging": "Slack",
            "database": "Supabase",
        },
        "composability_notes": "Generated on demand from idea data.",
    }


def _tact_spec_payload() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-vendor-risk-api001",
            "status": "approved",
            "domain": "healthcare",
            "category": "application",
        },
        "project": {
            "title": "Vendor Risk API",
            "workflow_context": "pre-release vendor review",
            "specific_user": "compliance automation owner",
            "buyer": "platform risk lead",
        },
        "solution": {
            "technical_approach": "FastAPI service with OpenAI summaries, Slack alerts, OAuth, and Datadog logs.",
            "suggested_stack": {
                "ai": "OpenAI",
                "messaging": "Slack",
                "database": "Supabase",
                "observability": "Datadog",
            },
        },
        "execution": {
            "risks": [
                "Patient PII must not leak to Slack or AI prompts.",
                "Vendor outage requires queue retry and manual fallback path.",
            ],
        },
        "artifacts": {
            "privacy_impact_assessment": {
                "personal_data": [
                    {"id": "patient_data", "label": "patient data"},
                    {"id": "email", "label": "email addresses"},
                ]
            },
            "data_classification": {
                "categories": [{"id": "regulated", "label": "regulated health data"}]
            },
            "deployment_topology": {
                "nodes": [{"name": "Datadog log drain", "provider": "Datadog"}],
                "notes": "Queue retry, fallback workflow, DPA, BAA, SLA, and SOC 2 evidence required.",
            },
        },
    }
