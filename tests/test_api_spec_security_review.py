"""API tests for TactSpec security review export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.security_review import SECURITY_REVIEW_SCHEMA_VERSION
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def spec_security_review_db(tmp_path) -> str:
    db_path = str(tmp_path / "spec_security_review_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_security_review_unit())
        store.insert_evaluation(_security_review_evaluation())
    finally:
        store.close()
    return db_path


@pytest.fixture
def spec_security_review_client(spec_security_review_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=spec_security_review_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_spec_security_review_returns_structured_json(
    spec_security_review_client: TestClient,
) -> None:
    response = spec_security_review_client.get("/api/v1/ideas/bu-sec-api001/security-review")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SECURITY_REVIEW_SCHEMA_VERSION
    assert payload["kind"] == "max.security_review"
    assert payload["source"]["idea_id"] == "bu-sec-api001"
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "Security Review API"
    assert payload["summary"]["finding_count"] == 7
    assert payload["summary"]["high_or_critical_finding_count"] >= 1
    assert "OAuth" in payload["security_context"]["detected_authentication_terms"]
    assert "Slack" in payload["security_context"]["detected_dependencies"]
    assert {finding["category"] for finding in payload["findings"]} >= {
        "authentication",
        "authorization",
        "secret_handling",
        "data_retention",
    }


def test_get_spec_security_review_markdown_format_query(
    spec_security_review_client: TestClient,
) -> None:
    response = spec_security_review_client.get(
        "/api/v1/ideas/bu-sec-api001/security-review?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-sec-api001-security-review.md"'
    )
    assert response.text.startswith("# Security Review API Security Review")
    assert "## Findings" in response.text
    assert "## Recommended Controls" in response.text
    assert "## Open Questions" in response.text
    assert "OAuth" in response.text
    assert "Slack" in response.text


def test_get_spec_security_review_markdown_download(
    spec_security_review_client: TestClient,
) -> None:
    response = spec_security_review_client.get("/api/v1/ideas/bu-sec-api001/security-review.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Security Review API Security Review")


def test_get_spec_security_review_missing_idea_returns_adjacent_not_found_shape(
    spec_security_review_client: TestClient,
) -> None:
    json_response = spec_security_review_client.get("/api/v1/ideas/bu-missing/security-review")
    markdown_response = spec_security_review_client.get(
        "/api/v1/ideas/bu-missing/security-review.md"
    )

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Idea not found: bu-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Idea not found: bu-missing"


def test_get_spec_security_review_unsupported_format_returns_validation_error(
    spec_security_review_client: TestClient,
) -> None:
    response = spec_security_review_client.get(
        "/api/v1/ideas/bu-sec-api001/security-review?format=yaml"
    )

    assert response.status_code == 422


def _security_review_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-sec-api001",
        title="Security Review API",
        one_liner="Expose security review artifacts to dashboard consumers",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem=(
            "Automation posts customer renewal exports into Slack without a durable "
            "security handoff."
        ),
        solution="Generate a deterministic security review from each TactSpec preview.",
        target_users="platform security reviewers",
        value_proposition="Security reviewers can automate signoff preparation.",
        specific_user="security automation owner",
        buyer="platform security lead",
        workflow_context="TactSpec generation to security dashboard ingestion",
        current_workaround="Manual OAuth, token, and customer data checks before build kickoff.",
        why_now="External dashboards need deterministic review artifacts.",
        validation_plan="Fetch JSON and Markdown review endpoints and verify section coverage.",
        first_10_customers="internal platform and security teams",
        domain_risks=[
            "Customer data retention and deletion rules can block launch.",
            "Slack webhook tokens must be rotated and redacted from logs.",
        ],
        evidence_rationale="Operational teams need traceable security review packets.",
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


def _security_review_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.4, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-sec-api001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=86.0,
        strengths=["Existing deterministic generator"],
        weaknesses=["Security signoff still needs review"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
