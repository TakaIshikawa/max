"""API tests for design brief ROI forecast exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_roi_forecast import SCHEMA_VERSION
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
            id="bu-roi-forecast-api",
            title="ROI Forecast API Lead",
            one_liner="Expose design brief ROI forecasts over REST.",
            category="application",
            problem="Dashboards cannot retrieve ROI forecast artifacts for approved briefs.",
            solution="Return deterministic ROI forecasts as JSON and Markdown.",
            value_proposition="Make payback and benefit ranges available to automation.",
            specific_user="portfolio operations lead",
            buyer="VP of Customer Operations",
            workflow_context="quarterly portfolio planning",
            current_workaround="manual spreadsheet payback modeling",
            why_now="Approved briefs need prioritization for execution planning.",
            validation_plan="Compare planning cycle time before and after forecast adoption.",
            first_10_customers="10 regulated customer operations teams",
            domain_risks=["Budget owners may require evidence before approving spend."],
            evidence_rationale="Operations leaders requested payback ranges for approved briefs.",
            evidence_signals=["sig-roi-api"],
            inspiring_insights=["ins-roi-api"],
            tech_approach="FastAPI endpoint backed by deterministic artifact generation.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            domain="operations",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="ROI Forecast API Brief",
                domain="operations",
                theme="roi-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=87.0,
                why_this_now="REST access lets dashboards consume ROI forecast artifacts.",
                merged_product_concept=(
                    "Expose deterministic design brief ROI forecasts over JSON and Markdown."
                ),
                synthesis_rationale="The ROI forecast module creates a stable planning artifact.",
                mvp_scope=["JSON ROI forecast endpoint", "Markdown ROI forecast export"],
                first_milestones=["Return structured ROI forecast from FastAPI"],
                validation_plan="Confirm the REST payload matches the ROI forecast renderer.",
                risks=["Benefit assumptions need buyer validation."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_roi_forecast_returns_json(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_roi_forecast_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/roi-forecast")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.roi_forecast"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "ROI Forecast API Brief"
    assert payload["summary"]["implementation_cost_low_usd"] > 0
    assert payload["summary"]["annual_benefit_low_usd"] > 0
    assert payload["payback_range"]["expected_months"] > 0
    assert payload["evidence_references"]


def test_get_design_brief_roi_forecast_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_roi_forecast_markdown_query_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/roi-forecast?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-ROI-Forecast-API-Brief-roi-forecast.md"'
    )
    assert response.text.startswith("# ROI Forecast: ROI Forecast API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Forecast Summary" in response.text
    assert "## Payback Range" in response.text
    assert "## Next Actions" in response.text


def test_get_design_brief_roi_forecast_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_roi_forecast_markdown_download_api.db")
    brief_id = _seed_design_brief(db_path)
    client = _client(db_path)

    query_response = client.get(
        f"/api/v1/design-briefs/{brief_id}/roi-forecast?format=markdown"
    )
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/roi-forecast.md")

    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert markdown_response.text == query_response.text


def test_get_design_brief_roi_forecast_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_roi_forecast_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/roi-forecast")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/roi-forecast.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_roi_forecast_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_roi_forecast_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)

    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/roi-forecast?format=yaml"
    )

    assert response.status_code == 422
