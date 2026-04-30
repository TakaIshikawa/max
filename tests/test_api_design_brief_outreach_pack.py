"""Tests for retrieving design brief outreach packs through the REST API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_outreach_pack import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_design_brief_outreach_pack_api.db")
    Store(db_path=path, wal_mode=True).close()
    return path


@pytest.fixture
def client(db_path: str) -> TestClient:
    from max.server.dependencies import get_store

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
            id="bu-api-outreach-lead",
            title="Outreach Pack API Lead",
            one_liner="Expose pilot outreach packs over REST.",
            category="application",
            problem="Validated ideas need concrete recruiting actions.",
            solution="Generate deterministic outreach packs.",
            value_proposition="Turn design briefs into pilot recruiting motion.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="pilot intake workflow",
            current_workaround="manual spreadsheet tracking",
            why_now="Validated specs need customer discovery.",
            validation_plan="Interview five workflow owners and recruit two pilots.",
            first_10_customers="developer platform teams",
            domain_risks=["Security review can delay pilots."],
            tech_approach="Python export module and REST endpoint.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-api-outreach-support",
            title="Outreach Pack API Support",
            one_liner="Track sponsor questions for pilot recruiting.",
            category="application",
            problem="Pilot discovery loses sponsor context.",
            solution="Persist qualification and follow-up artifacts.",
            value_proposition="Make pilot readiness auditable.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="customer discovery handoff",
            domain_risks=["Recruiting messages may target the wrong owner."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)

        return store.insert_design_brief(
            ProjectBrief(
                title="Outreach Pack API Brief",
                domain="developer-tools",
                theme="pilot-recruiting",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=88.0,
                why_this_now="Validation plans need pilot recruiting.",
                merged_product_concept="An outreach pack export for persisted design briefs.",
                synthesis_rationale="Completes customer discovery handoff.",
                mvp_scope=["JSON outreach pack", "Markdown outreach pack"],
                first_milestones=["Recruit first pilot"],
                validation_plan="Run discovery calls with five teams.",
                risks=["Security review can delay pilots."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_outreach_pack_returns_json_payload(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/outreach-pack")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.outreach_pack"
    assert data["design_brief"]["id"] == brief_id
    assert data["design_brief"]["source_idea_ids"] == [
        "bu-api-outreach-lead",
        "bu-api-outreach-support",
    ]
    assert [segment["id"] for segment in data["target_segments"]] == [
        "primary_workflow_owner",
        "economic_sponsors",
        "adjacent_evaluators",
    ]
    assert all(segment["source_idea_ids"] for segment in data["target_segments"])
    assert [hypothesis["id"] for hypothesis in data["outreach_hypotheses"]] == [
        "OH1",
        "OH2",
        "OH3",
    ]
    assert [template["id"] for template in data["templates"]] == [
        "email_primary_user",
        "dm_sponsor",
        "warm_intro",
    ]
    assert any(
        objection["id"] == "risk_or_trust" and "Security review" in objection["objection"]
        for objection in data["objection_handling"]
    )
    assert len(data["qualification_questions"]) == 6
    assert {idea["id"] for idea in data["source_ideas"]} == {
        "bu-api-outreach-lead",
        "bu-api-outreach-support",
    }


def test_get_design_brief_outreach_pack_supports_markdown_format(
    client: TestClient,
    db_path: str,
) -> None:
    brief_id = _seed_design_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/outreach-pack?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-outreach-pack.md"'
    )
    assert "# Outreach Pack: Outreach Pack API Brief" in response.text
    assert "## Target Segments" in response.text
    assert "## Outreach Hypotheses" in response.text


def test_get_design_brief_outreach_pack_missing_brief_returns_404(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/design-briefs/dbf-missing/outreach-pack")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
