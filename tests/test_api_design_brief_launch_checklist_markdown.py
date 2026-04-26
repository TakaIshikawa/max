"""API tests for design brief launch checklist exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def launch_checklist_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "design_brief_launch_checklist_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-launch-api-lead",
            title="Launch API Lead",
            one_liner="Expose launch readiness from design briefs.",
            category="application",
            problem="Execution handoffs need launch readiness.",
            solution="Add design brief launch checklist endpoints.",
            value_proposition="Give implementers a deterministic checklist.",
            specific_user="implementation lead",
            buyer="engineering manager",
            workflow_context="release planning",
            current_workaround="manual checklist docs",
            why_now="Design brief handoff exports already exist.",
            validation_plan="Fetch JSON and Markdown launch checklist endpoints.",
            first_10_customers="internal implementation leads",
            domain_risks=["Markdown can drift from JSON launch readiness."],
            tech_approach="FastAPI route and deterministic builder.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Launch Checklist API Brief",
                domain="developer-tools",
                theme="handoff-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=84.0,
                why_this_now="Launch readiness is needed before execution.",
                merged_product_concept="Design brief launch checklist export.",
                synthesis_rationale="Completes the handoff artifact set.",
                mvp_scope=["Launch checklist JSON", "Launch checklist Markdown"],
                first_milestones=["Return typed JSON", "Return downloadable Markdown"],
                validation_plan="Compare JSON sections with Markdown headings.",
                risks=["Checklist may omit rollout ownership."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def launch_checklist_client(launch_checklist_db: tuple[str, str]) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = launch_checklist_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_launch_checklist_json_success(
    launch_checklist_client: tuple[TestClient, str],
) -> None:
    client, brief_id = launch_checklist_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/launch-checklist")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max.design_brief.launch_checklist.v1"
    assert payload["kind"] == "max.design_brief.launch_checklist"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["summary"]["launch_gate"] == "ready_for_launch_review"
    assert [section["id"] for section in payload["sections"]] == [
        "readiness",
        "instrumentation",
        "validation",
        "rollout",
        "follow_up",
    ]
    assert payload["checklist_items"][0]["section_id"] == "readiness"
    assert payload["checklist_items"][0]["source_idea_ids"] == ["bu-launch-api-lead"]


def test_get_design_brief_launch_checklist_markdown_success(
    launch_checklist_client: tuple[TestClient, str],
) -> None:
    client, brief_id = launch_checklist_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/launch-checklist.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-launch-checklist.md"'
    )
    assert response.text.startswith("# Launch Checklist: Launch Checklist API Brief")
    assert "## Readiness" in response.text
    assert "## Instrumentation" in response.text
    assert "## Validation" in response.text
    assert "## Rollout" in response.text
    assert "## Follow-up" in response.text


def test_get_design_brief_launch_checklist_markdown_headings_match_json(
    launch_checklist_client: tuple[TestClient, str],
) -> None:
    client, brief_id = launch_checklist_client
    json_response = client.get(f"/api/v1/design-briefs/{brief_id}/launch-checklist")
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/launch-checklist.md")

    assert json_response.status_code == 200
    assert markdown_response.status_code == 200
    section_headings = [
        line.removeprefix("## ")
        for line in markdown_response.text.splitlines()
        if line.startswith("## ")
    ]
    assert section_headings == [section["title"] for section in json_response.json()["sections"]]


def test_get_design_brief_launch_checklist_json_missing_brief(
    launch_checklist_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = launch_checklist_client
    response = client.get("/api/v1/design-briefs/dbf-missing/launch-checklist")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_launch_checklist_markdown_missing_brief(
    launch_checklist_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = launch_checklist_client
    response = client.get("/api/v1/design-briefs/dbf-missing/launch-checklist.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
