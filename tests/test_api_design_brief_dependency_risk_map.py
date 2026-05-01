"""Tests for dependency risk map REST endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_dependency_risk_map import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_api_dependency_risk_map.db")
    store = Store(db_path=path, wal_mode=True)
    store.close()
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


@pytest.fixture
def seeded_brief_id(db_path: str) -> str:
    store = Store(db_path=db_path, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-api-dependency-risk",
            title="Dependency Risk API Idea",
            one_liner="Map external dependencies before build handoff.",
            category=BuildableCategory.APPLICATION,
            ideation_mode=IdeationMode.DIRECT,
            problem="Teams miss Salesforce, Slack, and customer data dependency risks.",
            solution="Generate dependency risk maps for review workflows.",
            value_proposition="Make dependency risks visible before implementation.",
            specific_user="customer success operator",
            buyer="customer success director",
            workflow_context="Salesforce to Slack renewal workflow",
            current_workaround="Manual Salesforce exports and Slack pings",
            why_now="External API automation is moving into autonomous build handoffs.",
            validation_plan="Run Salesforce sandbox sync and Slack notification dry run.",
            first_10_customers="customer success teams using Salesforce",
            domain_risks=["Security and privacy review may delay customer data access."],
            tech_approach="FastAPI webhook API with Salesforce, Slack, OAuth, and Postgres.",
            suggested_stack={
                "backend": "FastAPI",
                "crm": "Salesforce",
                "messaging": "Slack",
                "auth": "OAuth",
            },
            domain="customer-success",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        return store.insert_design_brief(
            ProjectBrief(
                title="Dependency Risk Brief",
                domain="customer-success",
                theme="dependency-risk",
                lead=Candidate(unit=unit),
                supporting=[],
                source_idea_ids=[unit.id],
                readiness_score=88.0,
                why_this_now="External API dependencies must be visible before build handoff.",
                merged_product_concept="A dependency risk map for Salesforce and Slack workflow handoffs.",
                synthesis_rationale="Links customer data, API, compliance, staffing, and launch risks.",
                mvp_scope=["Salesforce account sync", "Slack renewal notification"],
                first_milestones=["Run Salesforce sandbox handoff"],
                validation_plan="Run Salesforce sandbox sync and Slack notification dry run.",
                risks=["Security and privacy review may delay customer data access."],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_dependency_risk_map_json(
    client: TestClient,
    seeded_brief_id: str,
) -> None:
    resp = client.get(f"/api/v1/design-briefs/{seeded_brief_id}/dependency-risk-map")

    assert resp.status_code == 200
    data = resp.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["kind"] == "max.design_brief.dependency_risk_map"
    assert data["design_brief"]["id"] == seeded_brief_id
    assert data["summary"]["risk_count"] == 5
    assert data["dependency_risks"][0]["dependency_name"] == (
        "Salesforce, Slack, OAuth or SSO provider"
    )
    assert data["dependency_risks"][0]["severity"] == "high"
    assert data["dependency_context"]["detected_vendors"][:3] == [
        "Salesforce",
        "Slack",
        "OAuth or SSO provider",
    ]


def test_get_design_brief_dependency_risk_map_markdown_download(
    client: TestClient,
    seeded_brief_id: str,
) -> None:
    resp = client.get(f"/api/v1/design-briefs/{seeded_brief_id}/dependency-risk-map.md")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert resp.headers["content-disposition"] == (
        f'attachment; filename="{seeded_brief_id}-Dependency-Risk-Brief-dependency-risk-map.md"'
    )
    assert resp.text.startswith("# Dependency Risk Map: Dependency Risk Brief")
    assert f"Design brief: `{seeded_brief_id}`" in resp.text
    assert "### DBDR1: Salesforce, Slack, OAuth or SSO provider" in resp.text


def test_get_design_brief_dependency_risk_map_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/design-briefs/dbf-missing/dependency-risk-map")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Design brief not found: dbf-missing"}
