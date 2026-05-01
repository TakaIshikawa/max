"""API tests for design brief rollout communications plan exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_rollout_comms_plan import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.server.dependencies import get_store
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_rollout_comms_plan_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_design_brief(db_path: str, *, readiness_score: float = 84.0) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-api-rollout-comms-lead",
            title="Rollout Comms API",
            one_liner="Expose rollout communications guidance over REST.",
            category="application",
            problem="REST consumers cannot retrieve rollout communications plans.",
            solution="Add deterministic REST access to rollout comms artifacts.",
            value_proposition="Make launch messaging available to web clients.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="design-to-implementation handoff",
            current_workaround="manual launch notes",
            why_now="Design brief rollout comms exports already exist.",
            validation_plan="Call the rollout communications endpoint before launch.",
            first_10_customers="internal product operators",
            domain_risks=["Support readiness may lag the launch announcement."],
            evidence_signals=["sig-api-rollout-comms"],
            inspiring_insights=["ins-api-rollout-comms"],
            tech_approach="Python REST API with deterministic comms output",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)

        return store.insert_design_brief(
            ProjectBrief(
                title="Rollout Comms API",
                domain="developer-tools",
                theme="rollout-comms-plan",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=readiness_score,
                why_this_now="Design brief rollout comms exports already exist.",
                merged_product_concept="A rollout communications REST export for persisted design briefs.",
                synthesis_rationale="The REST surface should expose rollout messaging artifacts.",
                mvp_scope=["Rollout comms JSON", "Rollout comms Markdown"],
                first_milestones=["Register rollout communications route"],
                validation_plan="Call the rollout communications endpoint before launch.",
                risks=["Support readiness may lag the launch announcement."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_rollout_comms_plan_json(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path, readiness_score=48.0)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/rollout-comms-plan")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.rollout_comms_plan"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["title"] == "Rollout Comms API"
    assert data["summary"]["target_user"] == "product operator"
    assert [audience["id"] for audience in data["target_audiences"]] == [
        "internal_product_engineering",
        "internal_sales_success_support",
        "pilot_customers",
        "external_market",
    ]
    assert data["launch_phases"][0]["id"] == "prep"
    assert data["launch_phases"][0]["sequence"] == 1
    matrix_row = data["channel_message_matrix"][0]
    assert matrix_row["id"] == "RCM1"
    assert matrix_row["phase_id"] == "prep"
    assert matrix_row["audience_id"] == "internal_product_engineering"
    assert matrix_row["call_to_action"] == "Approve scope, owners, and rollback criteria."
    assert data["internal_enablement_notes"][0]["topic"] == "Positioning"
    announcement = data["customer_facing_announcement_drafts"][0]
    assert announcement["channel"] == "email"
    assert announcement["call_to_action"] == "Reply with a workflow owner and a first-use window."
    assert data["risk_faq_hooks"][0]["id"] == "FAQ1"
    assert {item["id"] for item in data["evidence_references"]} >= {
        "design_brief.why_this_now",
        "sig-api-rollout-comms",
        "ins-api-rollout-comms",
    }
    assert data["readiness_warnings"][0]["severity"] == "high"
    assert data["source_ideas"][0]["id"] == "bu-api-rollout-comms-lead"


def test_get_design_brief_rollout_comms_plan_markdown_download(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/rollout-comms-plan.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Rollout-Comms-API-rollout-comms-plan.md"'
    )
    assert response.text.startswith("# Rollout Communications Plan: Rollout Comms API")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Target Audiences" in response.text
    assert "## Channel Message Matrix" in response.text
    assert "## Customer-Facing Announcement Drafts" in response.text


def test_get_design_brief_rollout_comms_plan_missing_brief_returns_404_without_building_report(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("rollout comms report should not be built for missing briefs")

    monkeypatch.setattr(
        "max.server.api.build_design_brief_rollout_comms_plan",
        fail_if_called,
    )

    json_response = client.get("/api/v1/design-briefs/dbf-missing/rollout-comms-plan")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/rollout-comms-plan.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
