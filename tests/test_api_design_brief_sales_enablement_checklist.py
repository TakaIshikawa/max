"""API tests for design brief sales enablement checklist exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_sales_enablement_checklist import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


def _client(db_path: str) -> TestClient:
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
            id="bu-sales-enablement-api",
            title="Sales Enablement API Lead",
            one_liner="Expose seller preparation checklists over REST.",
            category="application",
            problem="Sales teams cannot retrieve operational checklists from design briefs.",
            solution="Return structured sales enablement checklist exports from the API.",
            value_proposition="Increase qualified demos and improve customer handoffs.",
            specific_user="sales engineer",
            buyer="VP of Revenue Operations",
            workflow_context="pre-demo qualification and handoff",
            current_workaround="spreadsheet qualification notes",
            why_now="Sales battlecards exist, but operational seller prep is still manual.",
            validation_plan="Run three pilot demos and compare handoff quality.",
            first_10_customers="B2B SaaS revenue teams with technical demos",
            domain_risks=["Prospects may object that demo prep adds sales cycle friction."],
            evidence_rationale="Seller interviews show inconsistent qualification capture.",
            evidence_signals=["sig-demo-quality"],
            inspiring_insights=["ins-sales-handoff"],
            tech_approach="FastAPI artifact export with deterministic JSON and Markdown.",
            suggested_stack={"backend": "FastAPI", "storage": "SQLite"},
            domain="sales",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Sales Enablement API Brief",
                domain="sales",
                theme="sales-readiness-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=88.0,
                why_this_now="Sales teams need operational prep before demos.",
                merged_product_concept=(
                    "A deterministic checklist for sales enablement and customer handoff."
                ),
                synthesis_rationale=(
                    "Connects buyer, qualification, proof, demo readiness, objections, and handoff."
                ),
                mvp_scope=["Qualification scorecard", "Demo prep checklist"],
                first_milestones=["Return checklist JSON"],
                validation_plan="Run three pilot demos and compare handoff quality.",
                risks=["Demo proof may not cover procurement concerns."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_sales_enablement_checklist_returns_structured_checklist(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_sales_enablement_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/sales-enablement-checklist"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.sales_enablement_checklist"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Sales Enablement API Brief"
    assert payload["summary"]["target_buyer"] == "VP of Revenue Operations"
    assert payload["summary"]["target_user"] == "sales engineer"
    assert payload["summary"]["sales_readiness_gate"] == "ready_for_seller_use"
    assert [section["id"] for section in payload["sections"]] == [
        "qualification",
        "discovery",
        "proof",
        "demo_readiness",
        "objection_handling",
        "handoff",
    ]
    assert payload["checklist_items"][0]["id"] == "DBSE1"
    assert payload["missing_evidence_actions"] == []


def test_get_design_brief_sales_enablement_checklist_markdown_returns_download(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_sales_enablement_markdown_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/sales-enablement-checklist.md"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Sales-Enablement-API-Brief-'
        'sales-enablement-checklist.md"'
    )
    assert response.text.startswith("# Sales Enablement Checklist: Sales Enablement API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Qualification" in response.text
    assert "## Demo Readiness" in response.text
    assert "## Missing Evidence Actions" in response.text


def test_get_design_brief_sales_enablement_checklist_missing_brief_returns_404_without_building(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "design_brief_sales_enablement_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    def fail_build(*_args, **_kwargs):
        raise AssertionError("sales enablement checklist builder was called")

    monkeypatch.setattr(
        "max.server.api.build_design_brief_sales_enablement_checklist",
        fail_build,
    )

    json_response = client.get(
        "/api/v1/design-briefs/dbf-missing/sales-enablement-checklist"
    )
    markdown_response = client.get(
        "/api/v1/design-briefs/dbf-missing/sales-enablement-checklist.md"
    )

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
