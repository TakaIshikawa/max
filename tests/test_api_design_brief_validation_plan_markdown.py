"""API tests for design brief validation plan Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def validation_plan_markdown_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "validation_plan_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-validation-plan-md-lead",
            title="Validation Plan Markdown Lead",
            one_liner="Export design brief validation plans as Markdown",
            category="application",
            problem="Handoff workflows need a readable validation artifact.",
            solution="Generate validation plan Markdown from persisted design briefs.",
            value_proposition="Give teams a deterministic review artifact.",
            specific_user="product engineer",
            buyer="engineering manager",
            workflow_context="design validation planning",
            current_workaround="manual validation notes",
            why_now="Persisted design briefs already expose validation plan JSON.",
            validation_plan="Review validation plan Markdown with product and engineering leads.",
            domain_risks=["Markdown exports may drift from JSON validation plan behavior."],
            tech_approach="FastAPI route using the existing validation plan renderer.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Validation Plan Markdown Brief",
                domain="developer-tools",
                theme="handoff-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=82.0,
                why_this_now="Teams need a human-readable validation plan export.",
                merged_product_concept="A direct Markdown export for design brief validation plans.",
                synthesis_rationale="Completes the artifact surface for handoffs.",
                mvp_scope=["Markdown validation plan export"],
                first_milestones=["Return validation plan Markdown from the API"],
                validation_plan="Confirm the response matches the existing validation renderer.",
                risks=["Markdown exports may drift from JSON validation plan behavior."],
                source_idea_ids=[lead.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def validation_plan_markdown_client(
    validation_plan_markdown_db: tuple[str, str],
) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = validation_plan_markdown_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_validation_plan_markdown_export_success(
    validation_plan_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = validation_plan_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/validation-plan.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Validation Plan: Validation Plan Markdown Brief")
    assert f"- **Design brief**: `{brief_id}`" in response.text
    assert "## Target User Hypotheses" in response.text
    assert "## Recruiting Criteria" in response.text
    assert "## Interview Script" in response.text
    assert "## Smoke-Test Landing Page Copy" in response.text
    assert "## Success Metrics" in response.text
    assert "Markdown validation plan export" in response.text


def test_get_design_brief_validation_plan_markdown_missing_brief(
    validation_plan_markdown_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = validation_plan_markdown_client
    response = client.get("/api/v1/design-briefs/dbf-missing/validation-plan.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
