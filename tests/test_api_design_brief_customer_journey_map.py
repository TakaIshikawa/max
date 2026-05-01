"""REST API tests for design brief customer journey map exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_customer_journey_map import SCHEMA_VERSION
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
            id="bu-customer-journey-api",
            title="Customer Journey API Lead",
            one_liner="Expose journey maps to REST consumers.",
            category="application",
            problem="Approved design briefs do not expose journey maps over REST.",
            solution="Return structured customer journey maps and Markdown exports.",
            value_proposition="Make adoption planning available to delivery teams.",
            specific_user="customer operations manager",
            buyer="customer success director",
            workflow_context="approved pilot onboarding",
            current_workaround="manual kickoff notes",
            why_now="Pilot approvals need customer journey planning before rollout.",
            validation_plan="Track first value, repeat usage, sponsor acceptance, and expansion readiness.",
            domain_risks=["Privacy approval can block customer data setup."],
            evidence_signals=["sig-customer-journey-api"],
            inspiring_insights=["ins-customer-journey-api"],
            domain="customer-success",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Customer Journey API Brief",
                domain="customer-success",
                theme="customer-journey-rest-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=88.0,
                why_this_now="Generated project specs need customer journey artifacts.",
                merged_product_concept="A customer journey map export for persisted design briefs.",
                synthesis_rationale="Connects pilot approval to adoption planning and expansion decisions.",
                mvp_scope=["Journey map JSON", "Journey map Markdown"],
                first_milestones=["Complete guided first-value journey"],
                validation_plan="Confirm customer teams can repeat the workflow without concierge help.",
                risks=["Privacy approval can block customer data setup."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_customer_journey_map_returns_structured_map(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_customer_journey_map_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(f"/api/v1/design-briefs/{brief_id}/customer-journey-map")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "max.design_brief.customer_journey_map"
    assert payload["design_brief"]["id"] == brief_id
    assert payload["design_brief"]["title"] == "Customer Journey API Brief"
    assert payload["summary"]["target_user"] == "customer operations manager"
    assert [stage["id"] for stage in payload["journey_stages"]] == [
        "JM1",
        "JM2",
        "JM3",
        "JM4",
        "JM5",
    ]
    assert payload["pain_points"]
    assert payload["moments_of_value"]
    assert payload["follow_up_actions"]
    assert payload["evidence_references"]


def test_get_design_brief_customer_journey_map_markdown_returns_attachment(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_customer_journey_map_markdown_api.db")
    brief_id = _seed_design_brief(db_path)
    response = _client(db_path).get(
        f"/api/v1/design-briefs/{brief_id}/customer-journey-map.md"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Customer-Journey-API-Brief-customer-journey-map.md"'
    )
    assert response.text.startswith("# Customer Journey Map: Customer Journey API Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Journey Stages" in response.text
    assert "## Pain Points" in response.text
    assert "## Moments of Value" in response.text
    assert "## Follow-up Actions" in response.text


def test_get_design_brief_customer_journey_map_missing_brief_returns_404_without_render(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = str(tmp_path / "design_brief_customer_journey_map_missing_api.db")
    Store(db_path=db_path, wal_mode=True).close()
    client = _client(db_path)

    def fail_render(*_args, **_kwargs):
        raise AssertionError("customer journey map renderer was called")

    monkeypatch.setattr("max.server.api.render_design_brief_customer_journey_map", fail_render)

    json_response = client.get("/api/v1/design-briefs/dbf-missing/customer-journey-map")
    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/customer-journey-map.md")

    assert json_response.status_code == 404
    assert json_response.json() == {"detail": "Design brief not found: dbf-missing"}
    assert markdown_response.status_code == 404
    assert markdown_response.json() == {"detail": "Design brief not found: dbf-missing"}


def test_design_brief_customer_journey_map_openapi_schema(tmp_path) -> None:
    db_path = str(tmp_path / "design_brief_customer_journey_map_openapi.db")
    schema = _client(db_path).get("/openapi.json").json()

    assert "DesignBriefCustomerJourneyMapResponse" in schema["components"]["schemas"]
    operation = schema["paths"]["/api/v1/design-briefs/{brief_id}/customer-journey-map"][
        "get"
    ]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/DesignBriefCustomerJourneyMapResponse")
