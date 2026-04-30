"""API tests for design brief sales battlecard exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_sales_battlecard import SCHEMA_VERSION
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
            id="bu-sales-battlecard-api",
            title="Sales Battlecard API Lead",
            one_liner="Expose sales battlecards over REST.",
            category="application",
            problem="Sales teams cannot retrieve battlecards from persisted planning artifacts.",
            solution="Return structured battlecards and Markdown exports from the API.",
            value_proposition="Help account teams convert design briefs into pilot conversations.",
            specific_user="account executive",
            buyer="revenue leader",
            workflow_context="pilot discovery call",
            current_workaround="manual sales notes",
            why_now="Downstream sales systems need deterministic handoff artifacts before launch.",
            validation_plan="Review battlecards with account teams and validate pilot objections.",
            domain_risks=["Security review can delay sales access."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Sales Battlecard API Brief",
                domain="developer-tools",
                theme="sales-battlecard-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=86.0,
                why_this_now="REST access lets sales tooling consume battlecards.",
                merged_product_concept="A sales battlecard export for persisted design briefs.",
                synthesis_rationale="Covers revenue handoff after product planning.",
                mvp_scope=["Sales battlecard JSON", "Sales battlecard Markdown"],
                first_milestones=["Return sales battlecard JSON"],
                validation_plan="Confirm account teams can handle pilot objections.",
                risks=["Security review can delay sales access."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_sales_battlecard_returns_structured_battlecard(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_sales_battlecard_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/sales-battlecard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.sales_battlecard"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Sales Battlecard API Brief"
    assert payload["design_brief"]["source_idea_ids"] == ["bu-sales-battlecard-api"]
    assert payload["summary"]["target_user"] == "account executive"
    assert payload["objection_handling"]
    assert any(row["id"] == "risk_or_trust" for row in payload["objection_handling"])
    assert payload["demo_beats"]


def test_get_design_brief_sales_battlecard_markdown_returns_downloadable_markdown(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_sales_battlecard_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/sales-battlecard.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-sales-battlecard.md"'
    )
    assert response.text.startswith("# Sales Battlecard: Sales Battlecard API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "Source ideas: bu-sales-battlecard-api" in response.text
    assert "## Objection Handling" in response.text
    assert "## Demo Beats" in response.text


def test_get_design_brief_sales_battlecard_missing_brief_returns_404_without_unrelated_builds(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "design_brief_sales_battlecard_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    def fail_unrelated_build(*_args, **_kwargs):
        raise AssertionError("unrelated design brief analysis builder was called")

    monkeypatch.setattr(
        "max.server.api.build_design_brief_pricing_strategy",
        fail_unrelated_build,
    )
    monkeypatch.setattr(
        "max.server.api.build_design_brief_technical_feasibility",
        fail_unrelated_build,
    )
    monkeypatch.setattr(
        "max.server.api.build_design_brief_evidence_matrix",
        fail_unrelated_build,
    )

    json_response = client.get("/api/v1/design-briefs/dbf-missing/sales-battlecard")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/sales-battlecard.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
