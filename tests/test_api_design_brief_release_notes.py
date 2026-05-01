"""REST tests for design brief release notes exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_release_notes import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def client(tmp_path) -> TestClient:
    db_path = str(tmp_path / "release_notes_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    from max.server.dependencies import get_store

    app = create_app()
    app.state.test_db_path = db_path

    def override_get_store():
        request_store = Store(db_path=db_path, wal_mode=True)
        try:
            yield request_store
        finally:
            request_store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_get_design_brief_release_notes_returns_json(client: TestClient) -> None:
    db_path = _client_db_path(client)
    brief_id = _seed_release_notes_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/release-notes")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.release_notes"
    assert data["design_brief"]["id"] == brief_id
    assert data["summary"]["release_stage"] == "ready_for_customer_rollout"
    assert data["summary"]["capability_count"] == 3
    assert data["customer_facing"]["shipped_capabilities"][0]["id"] == "CAP1"
    assert data["customer_facing"]["rollout_notes"][0]["stage"] == "Availability"
    assert data["customer_facing"]["known_limitations"][0]["id"] == "KL1"
    assert data["internal"]["validation_evidence"][0]["kind"] == "brief_field"
    assert data["internal"]["source_idea_ids"] == ["bu-api-release-notes"]
    assert data["source_ideas"][0]["id"] == "bu-api-release-notes"


def test_get_design_brief_release_notes_returns_markdown(client: TestClient) -> None:
    db_path = _client_db_path(client)
    brief_id = _seed_release_notes_brief(db_path)

    response = client.get(f"/api/v1/design-briefs/{brief_id}/release-notes?format=markdown")
    markdown_response = client.get(f"/api/v1/design-briefs/{brief_id}/release-notes.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.text == markdown_response.text
    assert response.text.startswith("# Release Notes: API Release Brief")
    assert f"Design brief: `{brief_id}`" in response.text
    assert "## Customer-Facing Notes" in response.text
    assert "### Rollout Notes" in response.text
    assert "### Validation Evidence" in response.text


def test_get_design_brief_release_notes_missing_brief(client: TestClient) -> None:
    response = client.get("/api/v1/design-briefs/dbf-missing/release-notes")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/release-notes.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404


def test_design_brief_release_notes_openapi_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "DesignBriefReleaseNotesResponse" in schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/design-briefs/{brief_id}/release-notes"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/DesignBriefReleaseNotesResponse"
    )
    assert any(param["name"] == "format" for param in operation["parameters"])


def _client_db_path(client: TestClient) -> str:
    return str(client.app.state.test_db_path)


def _seed_release_notes_brief(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-api-release-notes",
            title="API Release Notes Idea",
            one_liner="Expose release notes over REST.",
            category="application",
            problem="External clients cannot fetch deterministic handoff release notes.",
            solution="Serve structured and Markdown release notes from persisted design briefs.",
            value_proposition="Give launch teams stable release context without manual exports.",
            specific_user="implementation lead",
            buyer="customer success director",
            workflow_context="pilot launch handoff workflow",
            validation_plan="Review release notes with three implementation leads.",
            evidence_signals=["sig-release-notes"],
            inspiring_insights=["ins-release-notes"],
            domain_risks=["Launch scope may be misunderstood by customer-facing teams."],
            tech_approach="Python API with deterministic Markdown rendering.",
            suggested_stack={"language": "python", "api": "fastapi"},
            domain="customer-success",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="API Release Brief",
                domain="customer-success",
                theme="release-notes",
                lead=Candidate(unit=unit),
                readiness_score=84.0,
                why_this_now="Launch teams need stable handoff artifacts now.",
                merged_product_concept="Publish release notes that summarize shipped scope and rollout gates.",
                synthesis_rationale="REST consumers need the same artifact generated internally.",
                mvp_scope=[
                    "Structured release note JSON",
                    "Downloadable release note Markdown",
                    "Stable source idea references",
                ],
                first_milestones=["Validate Markdown download", "Confirm external client parsing"],
                validation_plan="Run client contract tests against seeded design briefs.",
                risks=["Release notes can overstate readiness if rollout gates are unclear."],
                source_idea_ids=[unit.id],
                design_status="approved",
            )
        )
    finally:
        store.close()
