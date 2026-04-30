"""API tests for design brief technical-feasibility exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_technical_feasibility import SCHEMA_VERSION
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
            id="bu-technical-feasibility-api",
            title="Technical Feasibility API Lead",
            one_liner="Expose design brief feasibility over REST",
            category="application",
            problem="Automation clients cannot read technical feasibility handoff reports.",
            solution="Return structured feasibility reports and Markdown exports from the API.",
            value_proposition="Make build-readiness decisions available to agents and dashboards.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="CI gate before autonomous implementation",
            why_now="Design brief artifacts already support downstream handoff workflows.",
            validation_plan="Review generated feasibility reports with engineering leads.",
            domain_risks=["Customer workflow data may include PII"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Technical Feasibility API Brief",
                domain="developer-tools",
                theme="rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=91.0,
                why_this_now="REST access lets agents consume feasibility before build assignment.",
                merged_product_concept=(
                    "Expose deterministic technical feasibility through a CLI, GitHub integration, "
                    "and API handoff."
                ),
                synthesis_rationale="The technical feasibility module creates a stable build handoff.",
                mvp_scope=["JSON technical feasibility endpoint", "Markdown feasibility export"],
                first_milestones=["Return structured feasibility from FastAPI"],
                validation_plan="Confirm the REST payload matches the technical feasibility renderer.",
                risks=["External API churn", "Customer workflow data may include PII"],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_technical_feasibility_returns_structured_report(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_technical_feasibility_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/technical-feasibility")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["source"]["entity_type"] == "design_brief"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Technical Feasibility API Brief"

    verdict = payload["feasibility_verdict"]
    assert verdict["verdict"] == "spike_required"
    assert verdict["risk_level"] == "high"
    assert "customer data handling" in " ".join(verdict["blocking_risks"])
    assert verdict["next_decision"].startswith("Complete the recommended spike plan")

    assumptions = payload["architecture_assumptions"]
    assert assumptions[0]["confidence"] == "medium"
    assert assumptions[0]["source_fields"] == ["merged_product_concept"]

    assert any(item["type"] == "external_api" for item in payload["integration_surface"])
    assert any(item["risk_level"] == "high" for item in payload["integration_surface"])
    assert any(item["risk_level"] == "high" for item in payload["data_dependencies"])
    assert payload["build_complexity"]["level"] == "high"
    assert payload["build_complexity"]["score"] == 10
    assert payload["build_complexity"]["constraints"]
    assert any(item["id"] == "U5" for item in payload["unknowns"])
    assert payload["recommended_spike_plan"][0]["id"] == "S1"
    assert payload["recommended_spike_plan"][0]["steps"]
    assert payload["recommended_spike_plan"][-1]["id"] == "S4"


def test_get_design_brief_technical_feasibility_markdown_returns_downloadable_markdown(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_technical_feasibility_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/technical-feasibility.md"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-technical-feasibility.md"'
    )
    assert response.text.startswith("# Technical Feasibility: Technical Feasibility API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Feasibility Verdict" in response.text
    assert "## Recommended Spike Plan" in response.text


def test_get_design_brief_technical_feasibility_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_technical_feasibility_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/technical-feasibility")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/technical-feasibility.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
