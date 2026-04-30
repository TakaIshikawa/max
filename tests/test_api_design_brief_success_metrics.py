"""API tests for design brief success metrics exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_success_metrics import SCHEMA_VERSION
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
            id="bu-success-metrics-api",
            title="Success Metrics API Lead",
            one_liner="Expose design brief success metrics over REST",
            category="application",
            problem="Dashboards cannot access design brief success metrics.",
            solution="Return structured success metrics and Markdown exports from the API.",
            value_proposition="Make design brief success criteria available to automation.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="design brief execution planning",
            why_now="Design brief artifacts already support downstream workflows.",
            validation_plan="Review generated metrics with product and engineering leads.",
            domain_risks=[],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Success Metrics API Brief",
                domain="developer-tools",
                theme="rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=88.0,
                why_this_now="REST access lets dashboards and agents consume metrics.",
                merged_product_concept=(
                    "Expose deterministic design brief success metrics over JSON and Markdown."
                ),
                synthesis_rationale="The success metrics module creates a stable execution artifact.",
                mvp_scope=["JSON success metrics endpoint", "Markdown success metrics endpoint"],
                first_milestones=["Return structured success metrics from FastAPI"],
                validation_plan="Confirm the REST payload matches the success metrics renderer.",
                risks=["Pilot metrics need buyer validation."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_success_metrics_returns_structured_report(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_success_metrics_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/success-metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["brief_id"] == brief_id
    assert payload["title"] == "Success Metrics API Brief"
    assert payload["north_star_metric"]["metric"] == "Qualified workflow success"
    assert payload["north_star_metric"]["confidence"] == "high"
    assert payload["activation_metrics"][0]["id"] == "A1"
    assert payload["retention_metrics"][0]["id"] == "R1"
    assert payload["validation_metrics"][2]["metric"] == "Readiness threshold"
    assert payload["risk_guardrails"][0]["id"] == "G1"
    assert payload["instrumentation_events"][0]["event"] == "success_metrics_report_generated"


def test_get_design_brief_success_metrics_markdown_returns_downloadable_markdown(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_success_metrics_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/success-metrics.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-success-metrics.md"'
    )
    assert response.text.startswith("# Success Metrics: Success Metrics API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## North Star Metric" in response.text
    assert "## Activation Metrics" in response.text
    assert "## Instrumentation Events" in response.text


def test_get_design_brief_success_metrics_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_success_metrics_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/success-metrics?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# Success Metrics: Success Metrics API Brief")


def test_get_design_brief_success_metrics_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_success_metrics_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/success-metrics")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/success-metrics.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_success_metrics_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_success_metrics_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/success-metrics?format=yaml"
    )

    assert response.status_code == 422
