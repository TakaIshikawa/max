"""API tests for design brief churn risk report exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_churn_risk_report import KIND, SCHEMA_VERSION
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
            id="bu-churn-risk-api",
            title="Churn Risk API Lead",
            one_liner="Expose design brief churn risk reports over REST.",
            category="application",
            problem="Customer success teams cannot see churn drivers for approved briefs.",
            solution="Return deterministic churn risk reports as JSON and Markdown.",
            value_proposition="Reduce retention risk with visible activation and renewal signals.",
            specific_user="customer success operations lead",
            buyer="VP of Customer Success",
            workflow_context="pilot onboarding and renewal planning",
            current_workaround="manual support ticket and budget review notes",
            why_now="Renewal planning needs a repeatable retention risk artifact.",
            validation_plan="Review activation, support, and pricing objections with five accounts.",
            first_10_customers="10 enterprise customer success teams",
            domain_risks=[
                "Support burden may delay adoption during onboarding.",
                "Procurement and budget approval may slow paid expansion.",
            ],
            evidence_rationale="Customer success leaders asked for retention risk summaries.",
            evidence_signals=[],
            inspiring_insights=[],
            domain="customer-success",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Churn Risk API Brief",
                domain="customer-success",
                theme="retention-risk-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=82.0,
                why_this_now="REST access lets lifecycle tools consume churn risk reports.",
                merged_product_concept=(
                    "Expose deterministic design brief churn risk reports over JSON and Markdown."
                ),
                synthesis_rationale="The churn risk module creates a stable lifecycle-risk artifact.",
                mvp_scope=[
                    "JSON churn risk report endpoint",
                    "Markdown churn risk report export",
                    "Support burden review",
                ],
                first_milestones=["Return structured churn risk report from FastAPI"],
                validation_plan="Confirm the REST payload matches the churn risk renderer.",
                risks=[
                    "Budget and procurement friction may delay conversion.",
                    "Onboarding support load may create churn risk.",
                ],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_churn_risk_report_returns_structured_report(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_churn_risk_report_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/churn-risk-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == KIND
    assert payload["design_brief"]["id"] == brief_id
    assert payload["summary"]["validation_status"] == "approved"
    assert payload["summary"]["support_burden"] in {"medium", "high"}
    assert payload["risk_drivers"]
    assert payload["retention_levers"]
    assert payload["follow_up_experiments"]
    assert payload["dimension_scores"]


def test_get_design_brief_churn_risk_report_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_churn_risk_report_markdown_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/churn-risk-report?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-churn-risk-report.md"'
    )
    assert response.text.startswith("# Churn Risk Report: Churn Risk API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert f"Kind: `{KIND}`" in response.text
    assert "## Risk Drivers" in response.text
    assert "## Retention Levers" in response.text
    assert "## Follow-Up Experiments" in response.text


def test_get_design_brief_churn_risk_report_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_churn_risk_report_download_api.db")
    brief_id = _seed_design_brief(db_path)
    client = _client(db_path)

    query_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/churn-risk-report?format=markdown"
    )
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/churn-risk-report.md")

    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert markdown_response.text == query_response.text


def test_get_design_brief_churn_risk_report_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_churn_risk_report_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/churn-risk-report")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/churn-risk-report.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_churn_risk_report_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_churn_risk_report_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/churn-risk-report?format=yaml"
    )

    assert response.status_code == 422
