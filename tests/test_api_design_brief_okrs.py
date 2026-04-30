"""API tests for design brief OKR exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

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
            id="bu-okrs-api",
            title="OKR API Lead",
            one_liner="Expose design brief OKRs over REST",
            category="application",
            problem="Dashboards cannot access design brief execution OKRs.",
            solution="Return structured OKRs and Markdown exports from the API.",
            value_proposition="Make execution goals available to automation.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="design brief execution planning",
            why_now="Design brief artifacts already support downstream workflows.",
            validation_plan="Review generated OKRs with product and engineering leads.",
            domain_risks=[],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="OKR API Brief",
                domain="developer-tools",
                theme="rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=88.0,
                why_this_now="REST access lets dashboards and agents consume OKRs.",
                merged_product_concept="Expose deterministic design brief OKRs over JSON and Markdown.",
                synthesis_rationale="The OKR module already creates a stable execution artifact.",
                mvp_scope=["JSON OKR endpoint", "Markdown OKR endpoint"],
                first_milestones=["Return structured OKRs from FastAPI"],
                validation_plan="Confirm the REST payload matches the OKR renderer.",
                risks=[],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_okrs_returns_structured_objectives(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_okrs_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/okrs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "max.design_brief.okrs.v1"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "OKR API Brief"
    assert payload["summary"]["objective_count"] == 4
    assert payload["summary"]["key_result_count"] == 12
    assert payload["summary"]["validation_required"] is True
    assert payload["objectives"][0]["id"] == "O1"
    assert payload["objectives"][0]["objective"] == "Validate demand for OKR API Brief"
    assert payload["objectives"][3]["id"] == "O4"
    assert payload["objectives"][0]["key_results"][0] == {
        "id": "KR1",
        "metric": "Interview at least 5 platform engineer",
        "target": "5 completed interviews",
        "evidence_source": "Customer discovery notes",
    }


def test_get_design_brief_okrs_markdown_returns_downloadable_markdown(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_okrs_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/okrs.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-okrs.md"'
    )
    assert response.text.startswith("# OKRs: OKR API Brief")
    assert "Schema: `max.design_brief.okrs.v1`" in response.text
    assert "## Objectives" in response.text
    assert "### O1: Validate demand for OKR API Brief" in response.text


def test_get_design_brief_okrs_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_okrs_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/okrs")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/okrs.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
