"""REST tests for design brief training plan exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_training_plan import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def client(tmp_path) -> TestClient:
    db_path = str(tmp_path / "training_plan_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    from max.server.dependencies import get_store

    app = create_app()
    app.state.test_db_path = db_path

    def override_get_store():
        request_store = Store(db_path=db_path, wal_mode=True)
        try:
            yield request_store
        finally:
            request_store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_design_brief_training_plan_returns_json(client: TestClient) -> None:
    db_path = _client_db_path(client)
    brief_id = _seed_training_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/training-plan")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.training_plan"
    assert data["design_brief"]["id"] == brief_id
    assert data["summary"]["buyer"] == "engineering director"
    assert [item["id"] for item in data["learning_objectives"]] == ["LO1", "LO2", "LO3", "LO4"]


def test_get_design_brief_training_plan_returns_markdown(client: TestClient) -> None:
    db_path = _client_db_path(client)
    brief_id = _seed_training_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/training-plan?format=markdown")
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/training-plan.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text == markdown_response.text
    assert response.text.startswith("# Training Plan: API Training Brief")
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Learning Objectives" in response.text


def test_get_design_brief_training_plan_missing_brief(client: TestClient) -> None:
    response = client.get("/api/v1/design-briefs/dbf-missing/training-plan")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/training-plan.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404


def test_design_brief_training_plan_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "DesignBriefTrainingPlanResponse" in schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/design-briefs/{brief_id}/training-plan"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DesignBriefTrainingPlanResponse"
    )
    assert any(param["name"] == "format" for param in operation["parameters"])


def _client_db_path(client: TestClient) -> str:
    return str(client.app.state.test_db_path)


def _seed_training_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-api-training",
            title="API Training Idea",
            one_liner="Expose training plans over REST.",
            category="application",
            problem="External agents cannot retrieve training artifacts.",
            solution="Serve deterministic training plans from persisted briefs.",
            value_proposition="Give UI clients a stable adoption artifact.",
            specific_user="platform lead",
            buyer="engineering director",
            workflow_context="developer platform adoption",
            validation_plan="Run training with two pilot teams.",
            evidence_signals=["sig-api-training"],
            inspiring_insights=["ins-api-training"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="API Training Brief",
                domain="developer-tools",
                theme="training-plan",
                lead=Candidate(unit=unit),
                readiness_score=84.0,
                why_this_now="API clients need consistent training access.",
                merged_product_concept="A REST endpoint for the training plan artifact.",
                synthesis_rationale="The artifact is already deterministic.",
                mvp_scope=["REST export", "Markdown export"],
                first_milestones=["Add endpoint"],
                validation_plan="Run training with two pilot teams.",
                risks=["Training owners may be unclear."],
                source_idea_ids=[unit.id],
                design_status="approved",
            )
        )
    finally:
        store.close()
