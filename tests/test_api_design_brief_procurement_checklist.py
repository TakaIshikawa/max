"""Tests for design brief procurement checklist REST exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_procurement_checklist import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_procurement_checklist_api.db")
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
            id="bu-procurement-api-lead",
            title="Procurement Checklist API Lead",
            one_liner="Prepare procurement handoffs from design briefs.",
            category="application",
            problem="Enterprise buyers need procurement artifacts before adoption.",
            solution="Export deterministic procurement checklists from persisted design briefs.",
            value_proposition="Reduce approval friction for organizational buyers.",
            specific_user="operations manager",
            buyer="VP of Operations",
            workflow_context="enterprise workflow rollout with customer data",
            current_workaround="manual vendor review documents",
            why_now="Generated ideas increasingly target organizational buyers.",
            validation_plan="Run procurement review with two pilot buyers.",
            first_10_customers="mid-market operations teams with formal procurement",
            domain_risks=[
                "Security and privacy review may delay customer data access.",
                "Budget owner may differ from the workflow sponsor.",
            ],
            evidence_rationale="Signals show budget, compliance, and procurement readiness gaps.",
            evidence_signals=[],
            inspiring_insights=[],
            tech_approach="FastAPI and persisted checklist generation with audit-friendly JSON.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Procurement Checklist Brief",
                domain="developer-tools",
                theme="procurement-readiness",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=86.0,
                why_this_now="Organizational buyers need procurement readiness before rollout.",
                merged_product_concept="A procurement checklist export for persisted design briefs.",
                synthesis_rationale=(
                    "Connects buyer, budget, compliance, support, and validation readiness."
                ),
                mvp_scope=["JSON procurement checklist", "Markdown procurement checklist"],
                first_milestones=["Return procurement checklist JSON"],
                validation_plan="Confirm procurement checklist traceability with budget owners.",
                risks=["Legal review is required before customer workflow data is used."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_procurement_checklist_json(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/procurement-checklist")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.procurement_checklist"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Procurement Checklist Brief"
    assert data["summary"]["procurement_gate"] == "ready_for_procurement_review"
    assert data["summary"]["section_count"] == 6
    assert data["checklist_items"][0]["id"] == "DBPC1"
    assert data["approval_gates"][0]["name"] == "Security review"


def test_get_design_brief_procurement_checklist_markdown_download(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/procurement-checklist.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Procurement-Checklist-Brief-procurement-checklist.md"'
    )
    assert response.text.startswith("# Procurement Checklist: Procurement Checklist Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Security Review" in response.text
    assert "## Approval Gates" in response.text


def test_get_design_brief_procurement_checklist_missing_brief_returns_404(
    client: TestClient,
) -> None:
    json_response = client.get("/api/v1/design-briefs/dbf-missing/procurement-checklist")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/procurement-checklist.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
