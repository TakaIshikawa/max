"""API tests for generated idea SLO plan export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import max.server.api as api
from max.server.app import create_app
from max.spec.slo_plan import SLO_PLAN_SCHEMA_VERSION
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def idea_slo_plan_db(tmp_path) -> str:
    db_path = str(tmp_path / "idea_slo_plan_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_slo_plan_unit())
        store.insert_evaluation(_slo_plan_evaluation())
    finally:
        store.close()
    return db_path


@pytest.fixture
def idea_slo_plan_client(idea_slo_plan_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=idea_slo_plan_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_idea_slo_plan_returns_structured_json(idea_slo_plan_client: TestClient) -> None:
    response = idea_slo_plan_client.get("/api/v1/ideas/bu-slo-api001/slo-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SLO_PLAN_SCHEMA_VERSION
    assert payload["kind"] == "max.slo_plan"
    assert payload["idea_id"] == "bu-slo-api001"
    assert payload["source"]["idea_id"] == "bu-slo-api001"
    assert payload["source"]["evaluation_available"] is True
    assert payload["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert payload["summary"]["title"] == "SLO Plan API"
    assert [objective["id"] for objective in payload["objectives"]] == [
        "SLO1",
        "SLO2",
        "SLO3",
        "SLO4",
    ]
    assert payload["error_budget_policy"]["budget_source_objective_id"] == "SLO1"
    assert payload["validation_steps"]


def test_get_idea_slo_plan_markdown_format_query(idea_slo_plan_client: TestClient) -> None:
    response = idea_slo_plan_client.get("/api/v1/ideas/bu-slo-api001/slo-plan?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-slo-api001-slo-plan.md"'
    )
    assert response.text.startswith("# SLO Plan API SLO Plan")
    assert "## Objectives" in response.text
    assert "### SLO1: availability" in response.text
    assert "## Error Budget Policy" in response.text
    assert "## Source Flags" in response.text


def test_get_idea_slo_plan_markdown_download(idea_slo_plan_client: TestClient) -> None:
    response = idea_slo_plan_client.get("/api/v1/ideas/bu-slo-api001/slo-plan.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-slo-api001-slo-plan.md"'
    )
    assert response.text.startswith("# SLO Plan API SLO Plan")


def test_get_idea_slo_plan_missing_idea_returns_404_without_generation(
    idea_slo_plan_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generate_slo_plan(*args, **kwargs):
        raise AssertionError("missing ideas must not generate SLO plans")

    monkeypatch.setattr(api, "generate_slo_plan", fail_generate_slo_plan)

    json_response = idea_slo_plan_client.get("/api/v1/ideas/bu-missing/slo-plan")
    markdown_response = idea_slo_plan_client.get("/api/v1/ideas/bu-missing/slo-plan.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Idea not found: bu-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Idea not found: bu-missing"


def test_get_idea_slo_plan_unsupported_format_returns_validation_error(
    idea_slo_plan_client: TestClient,
) -> None:
    response = idea_slo_plan_client.get("/api/v1/ideas/bu-slo-api001/slo-plan?format=yaml")

    assert response.status_code == 422


def _slo_plan_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-slo-api001",
        title="SLO Plan API",
        one_liner="Expose generated SLO plans to automation clients",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="API clients cannot fetch a focused SLO artifact for a persisted idea.",
        solution="Generate a deterministic SLO plan from the existing idea and spec preview.",
        target_users="platform automation teams",
        value_proposition="Operational readiness checks can consume SLO targets directly.",
        specific_user="release automation owner",
        buyer="platform operations lead",
        workflow_context="release readiness review",
        current_workaround="Clients parse the larger spec bundle and extract one nested artifact.",
        why_now="More launch workflows rely on direct REST artifact retrieval.",
        validation_plan="Fetch JSON and Markdown endpoints and verify SLO sections.",
        first_10_customers="internal release and operations teams",
        domain_risks=["SLO defaults may need owner review before production launch."],
        evidence_rationale="Existing spec generation already computes SLO plans.",
        tech_approach="FastAPI endpoint backed by deterministic spec generators.",
        suggested_stack={"backend": "FastAPI", "storage": "SQLite"},
        composability_notes="Generated on demand from existing idea persistence.",
    )


def _slo_plan_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.2, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-slo-api001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=84.0,
        strengths=["Existing deterministic SLO generator"],
        weaknesses=["Owners must still approve launch thresholds"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
