"""API tests for design brief analytics event dictionary exports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from max.analysis.design_brief_event_dictionary import SCHEMA_VERSION
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
            id="bu-event-dictionary-api",
            title="Event Dictionary API Lead",
            one_liner="Expose design brief analytics event dictionaries over REST.",
            category="application",
            problem="Analytics teams cannot consume generated event dictionaries.",
            solution="Return structured events and Markdown contracts from FastAPI.",
            value_proposition="Make success metric instrumentation consistent across builds.",
            specific_user="platform engineer",
            buyer="VP of Engineering",
            workflow_context="release governance review",
            why_now="Design briefs already capture scope, risks, and validation inputs.",
            validation_plan="Review event contracts with platform engineers before implementation.",
            domain_risks=["Security approval may block rollout."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Event Dictionary API Brief",
                domain="developer-tools",
                theme="event-dictionary-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=87.0,
                why_this_now="REST access lets analytics systems consume event dictionaries.",
                merged_product_concept=(
                    "A release governance analytics dictionary for persisted design briefs."
                ),
                synthesis_rationale="The event dictionary module creates a stable artifact.",
                mvp_scope=["JSON event dictionary export", "Markdown event dictionary export"],
                first_milestones=["Return event dictionaries from FastAPI"],
                validation_plan="Confirm REST payloads match the event dictionary renderer.",
                risks=[
                    "Security approval may block rollout.",
                    "Evidence notes may contain sensitive content.",
                ],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_event_dictionary_returns_structured_json(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_event_dictionary_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/event-dictionary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.event_dictionary"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Event Dictionary API Brief"
    assert payload["summary"]["event_group_count"] == 5
    assert payload["linked_metrics"]
    assert payload["event_groups"]
    assert payload["property_contracts"]
    assert {event["event_name"] for event in payload["events"]} >= {
        "design_brief_workflow_started",
        "design_brief_first_value_reached",
        "design_brief_risk_guardrail_triggered",
    }


def test_get_design_brief_event_dictionary_markdown_download(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_event_dictionary_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/event-dictionary.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Event-Dictionary-API-Brief-event-dictionary.md"'
    )
    assert response.text.startswith("# Analytics Event Dictionary: Event Dictionary API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Linked Metrics" in response.text
    assert "## Activation Events" in response.text
    assert "## Property Contracts" in response.text
    assert "### `workflow_context`" in response.text


def test_get_design_brief_event_dictionary_markdown_format_query(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_event_dictionary_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/event-dictionary?format=markdown"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Event-Dictionary-API-Brief-event-dictionary.md"'
    )
    assert "## Conversion Events" in response.text
    assert "`conversion_rate`" in response.text


def test_get_design_brief_event_dictionary_missing_brief_returns_404(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_event_dictionary_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/event-dictionary")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/event-dictionary.md")

    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_event_dictionary_unsupported_format_returns_validation_error(
    tmp_path,
) -> None:
    db_path = str(tmp_path / "design_brief_event_dictionary_invalid_format_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/event-dictionary?format=yaml"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported event dictionary format: yaml"
