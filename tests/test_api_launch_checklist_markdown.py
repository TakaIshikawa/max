"""API tests for launch checklist Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.spec.launch_checklist import generate_launch_checklist, render_launch_checklist_markdown
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def launch_checklist_markdown_db(tmp_path) -> str:
    db_path = str(tmp_path / "launch_checklist_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_buildable_unit(_markdown_unit())
        store.insert_evaluation(_markdown_evaluation())
    finally:
        store.close()
    return db_path


@pytest.fixture
def launch_checklist_markdown_client(launch_checklist_markdown_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=launch_checklist_markdown_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_launch_checklist_markdown_export_success(
    launch_checklist_markdown_client: TestClient,
) -> None:
    response = launch_checklist_markdown_client.get(
        "/api/v1/ideas/bu-launch-md001/launch-checklist.md"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        'attachment; filename="bu-launch-md001-launch-checklist.md"'
    )
    assert response.text.startswith("# Launch Checklist Markdown Export Launch Checklist")
    assert "## Repository Setup" in response.text
    assert "### LC1: Confirm package manager, runtime, and repository conventions before adding files." in response.text
    assert "- Status: pending" in response.text
    assert "- Owner: launch_owner" in response.text
    assert "- Evidence: Documented setup command or explicit deviation from suggested stack." in response.text


def test_get_launch_checklist_markdown_missing_idea(
    launch_checklist_markdown_client: TestClient,
) -> None:
    response = launch_checklist_markdown_client.get(
        "/api/v1/ideas/bu-missing/launch-checklist.md"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Idea not found: bu-missing"


def test_get_launch_checklist_markdown_headings_match_json_sections(
    launch_checklist_markdown_client: TestClient,
) -> None:
    json_response = launch_checklist_markdown_client.get(
        "/api/v1/ideas/bu-launch-md001/launch-checklist"
    )
    markdown_response = launch_checklist_markdown_client.get(
        "/api/v1/ideas/bu-launch-md001/launch-checklist.md"
    )

    assert json_response.status_code == 200
    assert markdown_response.status_code == 200
    section_headings = [
        line.removeprefix("## ")
        for line in markdown_response.text.splitlines()
        if line.startswith("## ") and line != "## Risks"
    ]
    assert section_headings == [section["title"] for section in json_response.json()["sections"]]


def test_render_launch_checklist_markdown_includes_item_readiness_context() -> None:
    checklist = generate_launch_checklist(_markdown_unit(), _markdown_evaluation())

    markdown = render_launch_checklist_markdown(checklist)

    assert "# Launch Checklist Markdown Export Launch Checklist" in markdown
    assert "- Launch gate: ready_for_launch_review" in markdown
    assert "### LC1: Confirm package manager, runtime, and repository conventions before adding files." in markdown
    assert "- Required: True" in markdown
    assert "- Rationale: Suggested stack: language=python, framework=fastapi." in markdown
    assert "- Evidence: Documented setup command or explicit deviation from suggested stack." in markdown


def _markdown_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-launch-md001",
        title="Launch Checklist Markdown Export",
        one_liner="Export launch checklist Markdown for implementation plans.",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Teams need launch checklists in release documents.",
        solution="Expose the deterministic launch checklist as Markdown.",
        target_users="implementation teams",
        value_proposition="Attach launch readiness directly to plans.",
        specific_user="release owner",
        buyer="engineering manager",
        workflow_context="release planning",
        current_workaround="copy JSON into docs manually",
        why_now="more launch artifacts are passed between tools",
        validation_plan="fetch JSON and Markdown endpoints and compare section headings",
        first_10_customers="internal release owners",
        domain_risks=["Markdown can drift from JSON checklist"],
        tech_approach="FastAPI route using the existing launch checklist generator.",
        suggested_stack={"language": "python", "framework": "fastapi"},
        status="approved",
    )


def _markdown_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.78, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-launch-md001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=83.0,
        strengths=["Stable Markdown handoff"],
        weaknesses=["Renderer needs parity tests"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
