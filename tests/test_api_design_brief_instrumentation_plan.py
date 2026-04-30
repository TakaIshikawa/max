"""API tests for design brief instrumentation plan exports."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from max.analysis.design_brief_instrumentation_plan import SCHEMA_VERSION
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
            id="bu-instrumentation-plan-api",
            title="Instrumentation Plan API Lead",
            one_liner="Expose design brief instrumentation plans over REST",
            category="application",
            problem="Dashboards cannot inspect design brief instrumentation plans.",
            solution="Return structured instrumentation plans and Markdown exports.",
            value_proposition="Make validation analytics visible to automation clients.",
            specific_user="platform engineer",
            buyer="VP of Engineering",
            workflow_context="release governance review",
            why_now="Agent releases are moving from experiments into production.",
            validation_plan="Interview platform engineers before implementation.",
            domain_risks=[],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Instrumentation Plan API Brief",
                domain="developer-tools",
                theme="instrumentation-plan-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=86.0,
                why_this_now="REST access lets dashboards consume instrumentation plans.",
                merged_product_concept=(
                    "A release governance brief with implementation-ready analytics."
                ),
                synthesis_rationale="The instrumentation module creates a stable artifact.",
                mvp_scope=["JSON instrumentation plan", "Markdown instrumentation plan"],
                first_milestones=["Return structured instrumentation plans from FastAPI"],
                validation_plan="Confirm the REST payload matches the instrumentation renderer.",
                risks=[
                    "Security approval may block rollout.",
                    "Analytics gaps may hide failed reviews.",
                ],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_instrumentation_plan_returns_structured_json(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_instrumentation_plan_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/instrumentation-plan"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.instrumentation_plan"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Instrumentation Plan API Brief"
    assert payload["summary"]["activation_event_count"] >= 1
    assert payload["events"]
    assert payload["activation_funnel_steps"]
    assert payload["retention_checkpoints"]
    assert payload["guardrail_alerts"]
    assert "missing_inputs" in payload
    assert {event["name"] for event in payload["events"]} >= {
        "activation_started",
        "first_value_reached",
        "core_workflow_repeated",
        "guardrail_alert_triggered",
    }


def test_get_design_brief_instrumentation_plan_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_instrumentation_plan_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/instrumentation-plan.md"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-instrumentation-plan.md"'
    )
    assert response.text.startswith("# Instrumentation Plan: Instrumentation Plan API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Events" in response.text
    assert "## Activation Funnel" in response.text
    assert "## Guardrail Alerts" in response.text


def test_get_design_brief_instrumentation_plan_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_instrumentation_plan_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/instrumentation-plan?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-instrumentation-plan.md"'
    )
    assert response.text.startswith("# Instrumentation Plan: Instrumentation Plan API Brief")


def test_get_design_brief_instrumentation_plan_missing_brief_returns_404_without_rendering(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_instrumentation_plan_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    with patch(
        "max.server.api.render_design_brief_instrumentation_plan"
    ) as render, patch("max.server.api.build_design_brief_instrumentation_plan") as build:
        json_response = client.get("/api/v1/design-briefs/dbf-missing/instrumentation-plan")
        markdown_response = client.get(
            "/api/v1/design-briefs/dbf-missing/instrumentation-plan.md"
        )

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
    build.assert_not_called()
    render.assert_not_called()


def test_get_design_brief_instrumentation_plan_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_instrumentation_plan_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/instrumentation-plan?format=yaml"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported instrumentation plan format: yaml"
