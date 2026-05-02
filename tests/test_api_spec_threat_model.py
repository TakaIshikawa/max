"""API tests for TactSpec threat model export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.threat_model import THREAT_MODEL_SCHEMA_VERSION
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def spec_threat_model_db(tmp_path) -> str:
    db_path = str(tmp_path / "spec_threat_model_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_threat_model_unit())
        store.insert_evaluation(_threat_model_evaluation())
    finally:
        store.close()
    return db_path


@pytest.fixture
def spec_threat_model_client(spec_threat_model_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=spec_threat_model_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_spec_threat_model_returns_structured_json(
    spec_threat_model_client: TestClient,
) -> None:
    response = spec_threat_model_client.get("/api/v1/ideas/bu-threat-api001/threat-model")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == THREAT_MODEL_SCHEMA_VERSION
    assert payload["kind"] == "max.threat_model"
    assert payload["idea_id"] == "bu-threat-api001"
    assert payload["scope"]["title"] == "Threat Model API"
    assert payload["scope"]["evaluation_available"] is True
    assert payload["assets"]
    assert payload["trust_boundaries"]
    assert payload["threat_scenarios"]
    assert payload["mitigations"]
    assert payload["review_gate"]["decision"] in {"ready_for_review", "needs_security_review"}
    assert {scenario["id"] for scenario in payload["threat_scenarios"]} >= {
        "THR1",
        "THR2",
        "THR3",
        "THR4",
    }


def test_get_spec_threat_model_markdown_format_query(
    spec_threat_model_client: TestClient,
) -> None:
    response = spec_threat_model_client.get(
        "/api/v1/ideas/bu-threat-api001/threat-model?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-threat-api001-threat-model.md"'
    )
    assert response.text.startswith("# Threat Model API Threat Model")
    assert "- Schema version: max-threat-model/v1" in response.text
    assert "- Idea ID: bu-threat-api001" in response.text
    assert "## Assets" in response.text
    assert "## Trust Boundaries" in response.text
    assert "## Threat Scenarios" in response.text
    assert "## Mitigations" in response.text
    assert "## Review Gate" in response.text
    assert "OAuth" in response.text
    assert "Slack" in response.text


def test_get_spec_threat_model_markdown_download(
    spec_threat_model_client: TestClient,
) -> None:
    query_response = spec_threat_model_client.get(
        "/api/v1/ideas/bu-threat-api001/threat-model?format=markdown"
    )
    suffix_response = spec_threat_model_client.get(
        "/api/v1/ideas/bu-threat-api001/threat-model.md"
    )

    assert suffix_response.status_code == 200
    assert suffix_response.headers["content-type"].startswith("text/markdown")
    assert suffix_response.headers["content-disposition"] == (
        'attachment; filename="bu-threat-api001-threat-model.md"'
    )
    assert suffix_response.text == query_response.text


def test_get_spec_threat_model_missing_idea_returns_adjacent_not_found_shape(
    spec_threat_model_client: TestClient,
) -> None:
    json_response = spec_threat_model_client.get("/api/v1/ideas/bu-missing/threat-model")
    markdown_response = spec_threat_model_client.get("/api/v1/ideas/bu-missing/threat-model.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Idea not found: bu-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Idea not found: bu-missing"


def test_get_spec_threat_model_unsupported_format_returns_validation_error(
    spec_threat_model_client: TestClient,
) -> None:
    response = spec_threat_model_client.get(
        "/api/v1/ideas/bu-threat-api001/threat-model?format=yaml"
    )

    assert response.status_code == 422


def _threat_model_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-threat-api001",
        title="Threat Model API",
        one_liner="Expose threat model artifacts to dashboard consumers",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem=(
            "Automation posts customer renewal exports into Slack without a durable "
            "threat model handoff."
        ),
        solution="Generate a deterministic threat model from each TactSpec preview.",
        target_users="platform security reviewers",
        value_proposition="Security reviewers can automate threat model preparation.",
        specific_user="security automation owner",
        buyer="platform security lead",
        workflow_context="TactSpec generation to security dashboard ingestion",
        current_workaround="Manual OAuth, token, and customer data checks before build kickoff.",
        why_now="External dashboards need deterministic review artifacts.",
        validation_plan="Fetch JSON and Markdown threat model endpoints and verify section coverage.",
        first_10_customers="internal platform and security teams",
        domain_risks=[
            "Customer data retention and deletion rules can block launch.",
            "Slack webhook tokens must be rotated and redacted from logs.",
        ],
        evidence_rationale="Operational teams need traceable threat model packets.",
        tech_approach=(
            "FastAPI endpoint using OAuth, SSO, RBAC scopes, webhook signature checks, "
            "audit logs, rate limits, encrypted secret storage, and Postgres."
        ),
        suggested_stack={
            "backend": "FastAPI",
            "auth": "OAuth",
            "database": "Postgres",
            "messaging": "Slack",
        },
        composability_notes="Generated from the existing spec preview without extra persistence.",
    )


def _threat_model_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.4, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-threat-api001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=86.0,
        strengths=["Existing deterministic generator"],
        weaknesses=["Threat model signoff still needs review"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
