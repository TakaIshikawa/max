"""API tests for design brief PRD exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_prd import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def prd_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "prd_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        signal = Signal(
            id="sig-api-prd",
            source_type=SignalSourceType.ARTICLE,
            source_adapter="test",
            title="PRD export evidence",
            content="A source item supporting PRD export evidence.",
            url="https://example.com/api-prd",
            metadata={"signal_role": "problem"},
        )
        store.insert_signal(signal)
        lead = BuildableUnit(
            id="bu-api-prd-lead",
            title="API PRD Lead",
            one_liner="Export design brief PRDs",
            category="application",
            problem="Design agents need compact product requirements.",
            solution="Expose JSON and Markdown PRD exports.",
            value_proposition="Give handoff agents a deterministic artifact.",
            specific_user="product designer",
            buyer="head of product",
            workflow_context="design brief handoff",
            current_workaround="manual PRD notes",
            why_now="Design briefs are already persisted.",
            validation_plan="Review PRD exports with product and design agents.",
            domain_risks=["Evidence links may be lost in export."],
            evidence_rationale="A source signal supports PRD export demand.",
            evidence_signals=[signal.id],
            tech_approach="FastAPI route using a deterministic renderer.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="API PRD Brief",
                domain="developer-tools",
                theme="handoff-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=83.0,
                why_this_now="Teams need a compact PRD export.",
                merged_product_concept="A direct PRD export for design briefs.",
                synthesis_rationale="Completes the handoff artifact surface.",
                mvp_scope=["PRD JSON endpoint", "PRD Markdown endpoint"],
                first_milestones=["Return PRD Markdown from the API"],
                validation_plan="Confirm the response includes source evidence.",
                risks=["Markdown output may drift from JSON output."],
                source_idea_ids=[lead.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def prd_client(prd_db: tuple[str, str]) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = prd_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_prd_structured_response(prd_client: tuple[TestClient, str]) -> None:
    client, brief_id = prd_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/prd")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert set(data["sections"]) >= {
        "title",
        "user_buyer",
        "problem",
        "proposed_workflow",
        "non_goals",
        "success_metrics",
        "mvp_scope",
        "dependencies",
        "risks",
        "evidence_links",
    }
    assert "https://example.com/api-prd" in "\n".join(
        data["sections"]["evidence_links"]["content"]
    )


def test_get_design_brief_prd_markdown_export_success(
    prd_client: tuple[TestClient, str],
) -> None:
    client, brief_id = prd_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/prd.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-prd.md"'
    )
    assert response.text.startswith("# PRD: API PRD Brief")
    assert "## User / Buyer" in response.text
    assert "## Problem" in response.text
    assert "## Evidence Links" in response.text
    assert "https://example.com/api-prd" in response.text


def test_get_design_brief_prd_missing_brief(prd_client: tuple[TestClient, str]) -> None:
    client, _brief_id = prd_client

    json_response = client.get("/api/v1/design-briefs/dbf-missing/prd")
    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"

    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/prd.md")
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
