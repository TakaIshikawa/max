"""API tests for design brief GTM channel plan exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_gtm_channel_plan import SCHEMA_VERSION
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
            id="bu-gtm-channel-plan-api",
            title="GTM Channel Plan API Lead",
            one_liner="Expose design brief GTM channel plans over REST",
            category="application",
            problem="Launch dashboards cannot inspect channel recommendations.",
            solution="Return structured GTM channel plans and Markdown exports.",
            value_proposition="Make launch planning available to automation.",
            specific_user="developer tools founder",
            buyer="growth lead",
            workflow_context="design partner recruiting",
            why_now="Launch-planning artifacts are ready for external dashboards.",
            validation_plan="Review channel priorities with two launch owners.",
            domain_risks=["Message-market fit may vary by channel."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="GTM Channel Plan API Brief",
                domain="developer-tools",
                theme="gtm-channel-plan-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=87.0,
                why_this_now="REST access lets dashboards consume channel plans.",
                merged_product_concept="A deterministic launch channel plan for design briefs.",
                synthesis_rationale="The GTM channel module creates a stable launch artifact.",
                mvp_scope=["JSON GTM channel plan", "Markdown GTM channel plan"],
                first_milestones=["Return structured channel recommendations from FastAPI"],
                validation_plan="Confirm the REST payload preserves nested recommendation fields.",
                risks=["Message-market fit may vary by channel."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_gtm_channel_plan_returns_structured_json(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_gtm_channel_plan_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/gtm-channel-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.gtm_channel_plan"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "GTM Channel Plan API Brief"
    assert payload["summary"]["primary_channel"] == "design partner outreach"
    assert [item["id"] for item in payload["channel_recommendations"]] == [
        "GTM1",
        "GTM2",
        "GTM3",
    ]
    first_recommendation = payload["channel_recommendations"][0]
    assert first_recommendation["success_metric"]["metric"] == "qualified_conversation_rate"
    assert first_recommendation["tactics"][0]["owner"] == "product marketing"
    assert first_recommendation["source_idea_ids"] == ["bu-gtm-channel-plan-api"]
    assert payload["launch_sequence"][0]["channels"] == [
        "design partner outreach",
        "buyer enablement content",
    ]


def test_get_design_brief_gtm_channel_plan_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_gtm_channel_plan_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/gtm-channel-plan.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-gtm-channel-plan.md"'
    )
    assert response.text.startswith("# GTM Channel Plan: GTM Channel Plan API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Channel Recommendations" in response.text
    assert "design partner outreach" in response.text
    assert "## Measurement Plan" in response.text


def test_get_design_brief_gtm_channel_plan_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_gtm_channel_plan_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/gtm-channel-plan")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/gtm-channel-plan.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
