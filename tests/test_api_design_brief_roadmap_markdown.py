"""API tests for design brief roadmap Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def roadmap_markdown_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "roadmap_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-roadmap-md-lead",
            title="Roadmap Markdown Lead",
            one_liner="Export design brief roadmaps as Markdown",
            category="application",
            problem="Handoff workflows need a readable roadmap artifact.",
            solution="Generate phased roadmap Markdown from persisted design briefs.",
            value_proposition="Give humans a deterministic planning handoff.",
            specific_user="product engineer",
            buyer="engineering manager",
            workflow_context="design handoff planning",
            current_workaround="manual roadmap notes",
            why_now="Persisted design briefs already expose roadmap JSON.",
            validation_plan="Review roadmap Markdown with product and engineering leads.",
            domain_risks=["Markdown exports may drift from JSON roadmap behavior."],
            tech_approach="FastAPI route using the existing deterministic renderer.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Roadmap Markdown Brief",
                domain="developer-tools",
                theme="handoff-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=82.0,
                why_this_now="Teams need a human-readable roadmap export.",
                merged_product_concept="A direct Markdown export for design brief roadmaps.",
                synthesis_rationale="Completes the artifact surface for handoffs.",
                mvp_scope=["Markdown roadmap export"],
                first_milestones=["Return roadmap Markdown from the API"],
                validation_plan="Confirm the response matches the existing roadmap renderer.",
                risks=["Markdown exports may drift from JSON roadmap behavior."],
                source_idea_ids=[lead.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def roadmap_markdown_client(roadmap_markdown_db: tuple[str, str]) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = roadmap_markdown_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_roadmap_markdown_export_success(
    roadmap_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = roadmap_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/roadmap.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-roadmap.md"'
    )
    assert response.text.startswith("# Roadmap: Roadmap Markdown Brief")
    assert "## Discovery" in response.text
    assert "## Prototype" in response.text
    assert "## Validation" in response.text
    assert "## Beta" in response.text
    assert "## Launch" in response.text


def test_get_design_brief_roadmap_markdown_missing_brief(
    roadmap_markdown_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = roadmap_markdown_client
    response = client.get("/api/v1/design-briefs/dbf-missing/roadmap.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"

