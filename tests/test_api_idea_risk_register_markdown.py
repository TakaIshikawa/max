"""API tests for idea risk register Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def idea_risk_register_markdown_db(tmp_path) -> str:
    db_path = str(tmp_path / "idea_risk_register_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-risk-md001",
                source_type=SignalSourceType.FORUM,
                source_adapter="test",
                title="Risk register signal",
                content="Implementation teams need risk registers in planning documents.",
                url="https://example.com/risk-register-md",
                credibility=0.82,
            )
        )
        store.insert_insight(
            Insight(
                id="ins-risk-md001",
                category=InsightCategory.GAP,
                title="Risk register insight",
                summary="PR planning works better when risk details are readable.",
                evidence=["sig-risk-md001"],
                confidence=0.84,
                domains=["planning"],
            )
        )
        store.insert_buildable_unit(_markdown_unit())
        store.insert_evaluation(_markdown_evaluation())
    finally:
        store.close()
    return db_path


@pytest.fixture
def idea_risk_register_markdown_client(
    idea_risk_register_markdown_db: str,
) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=idea_risk_register_markdown_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_idea_risk_register_json_unchanged(
    idea_risk_register_markdown_client: TestClient,
) -> None:
    response = idea_risk_register_markdown_client.get(
        "/api/v1/ideas/bu-risk-md001/risk-register"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    payload = response.json()
    assert payload["schema_version"] == "max-risk-register/v1"
    assert payload["kind"] == "max.risk_register"
    assert payload["idea_id"] == "bu-risk-md001"
    assert payload["summary"]["title"] == "Risk Register Markdown"
    assert isinstance(payload["risks"], list)
    assert "validation_triggers" in payload


def test_get_idea_risk_register_format_markdown(
    idea_risk_register_markdown_client: TestClient,
) -> None:
    response = idea_risk_register_markdown_client.get(
        "/api/v1/ideas/bu-risk-md001/risk-register?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-risk-md001-risk-register.md"'
    )
    assert response.text.startswith("# Risk Register Markdown Risk Register")
    assert "- Schema version: max-risk-register/v1" in response.text
    assert "- Idea ID: bu-risk-md001" in response.text
    assert "## Summary" in response.text
    assert "- Risk count:" in response.text
    assert "## Prioritized Risks" in response.text
    assert "- Severity: high" in response.text
    assert "- Likelihood: likely" in response.text
    assert "- Evidence references:" in response.text
    assert "- insight:ins-risk-md001" in response.text
    assert "- signal:sig-risk-md001" in response.text
    assert "- Mitigations:" in response.text
    assert "- Validation trigger:" in response.text


def test_get_idea_risk_register_markdown_export_success(
    idea_risk_register_markdown_client: TestClient,
) -> None:
    query_response = idea_risk_register_markdown_client.get(
        "/api/v1/ideas/bu-risk-md001/risk-register?format=markdown"
    )
    suffix_response = idea_risk_register_markdown_client.get(
        "/api/v1/ideas/bu-risk-md001/risk-register.md"
    )

    assert suffix_response.status_code == 200
    assert suffix_response.headers["content-type"].startswith("text/markdown")
    assert suffix_response.headers["content-disposition"] == (
        'attachment; filename="bu-risk-md001-risk-register.md"'
    )
    assert suffix_response.text == query_response.text


def test_get_idea_risk_register_markdown_missing_idea(
    idea_risk_register_markdown_client: TestClient,
) -> None:
    response = idea_risk_register_markdown_client.get(
        "/api/v1/ideas/bu-missing/risk-register.md"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def test_get_idea_risk_register_invalid_format(
    idea_risk_register_markdown_client: TestClient,
) -> None:
    response = idea_risk_register_markdown_client.get(
        "/api/v1/ideas/bu-risk-md001/risk-register?format=yaml"
    )

    assert response.status_code == 422


def _markdown_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-risk-md001",
        title="Risk Register Markdown",
        one_liner="Export idea risk registers as Markdown.",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Teams need risk registers in handoff documents.",
        solution="Expose the existing deterministic risk register as Markdown.",
        target_users="implementation teams",
        value_proposition="Make risk review easy to attach to PR planning.",
        specific_user="implementation lead",
        buyer="engineering manager",
        workflow_context="PR planning",
        current_workaround="copy JSON risk fields into docs manually",
        why_now="more implementation artifacts are consumed as Markdown",
        validation_plan="fetch JSON and Markdown endpoints and compare risk order",
        first_10_customers="internal implementation leads",
        domain_risks=["Markdown can drift from structured risk data"],
        evidence_rationale="Evidence shows handoff documents need readable risk details.",
        inspiring_insights=["ins-risk-md001"],
        evidence_signals=["sig-risk-md001"],
        tech_approach="FastAPI route using the existing risk register generator.",
        suggested_stack={"language": "python", "framework": "fastapi"},
        status="approved",
    )


def _markdown_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.75, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-risk-md001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=82.0,
        strengths=["Readable handoff"],
        weaknesses=[],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
