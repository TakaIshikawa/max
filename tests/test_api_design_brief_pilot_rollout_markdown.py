"""Tests for design brief pilot rollout REST exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_pilot_rollout import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_pilot_rollout_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_design_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-api-pilot-lead",
            title="Pilot Rollout API",
            one_liner="Expose pilot rollout guidance over REST.",
            category="application",
            problem="REST consumers cannot retrieve staged rollout plans.",
            solution="Add deterministic REST access to pilot rollout artifacts.",
            value_proposition="Make rollout readiness available to web clients.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="design-to-implementation handoff",
            current_workaround="manual pilot notes",
            why_now="Design brief pilot rollout exports already exist.",
            validation_plan="Call the REST pilot rollout endpoint before launch.",
            first_10_customers="internal product operators",
            domain_risks=["Privacy review is required before customer workflow data is used."],
            evidence_signals=["sig-api-pilot"],
            inspiring_insights=["ins-api-pilot"],
            tech_approach="Python REST API with deterministic rollout output",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)

        return store.insert_design_brief(
            ProjectBrief(
                title="Pilot Rollout API",
                domain="developer-tools",
                theme="pilot-rollout",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=84.0,
                why_this_now="Design brief pilot rollout exports already exist.",
                merged_product_concept="A pilot rollout REST export for persisted design briefs.",
                synthesis_rationale="The REST surface should expose staged rollout artifacts.",
                mvp_scope=["Pilot rollout JSON", "Pilot rollout Markdown"],
                first_milestones=["Register pilot rollout route"],
                validation_plan="Call the REST pilot rollout endpoint before launch.",
                risks=["Privacy review is required before customer workflow data is used."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_pilot_rollout_json(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/pilot-rollout")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.pilot_rollout"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Pilot Rollout API"
    assert data["pilot_cohort"]["target_users"] == "product operator"
    assert data["entry_criteria"]
    assert [phase["id"] for phase in data["rollout_phases"]] == [
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
    ]
    assert data["success_thresholds"]


def test_get_design_brief_pilot_rollout_markdown_download(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/pilot-rollout.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Pilot-Rollout-API-pilot-rollout.md"'
    )
    assert response.text.startswith("# Pilot Rollout Plan: Pilot Rollout API")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Rollout Phases" in response.text
    assert "## Success Thresholds" in response.text


def test_get_design_brief_pilot_rollout_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/pilot-rollout")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/pilot-rollout.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
