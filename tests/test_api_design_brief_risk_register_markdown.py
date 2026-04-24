"""API tests for design brief risk register Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_risk_register import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _unit(unit_id: str, *, domain_risks: list[str], evidence_signals: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Risk Markdown Source {unit_id}",
        one_liner="Risk markdown source idea",
        category="application",
        problem="Teams need safer implementation handoffs.",
        solution="Consolidate design risks before build.",
        value_proposition="Reduce avoidable execution risk.",
        specific_user="product engineer",
        buyer="engineering manager",
        workflow_context="design handoff review",
        current_workaround="spreadsheet review",
        why_now="Design synthesis is being persisted.",
        validation_plan="Interview implementers.",
        domain_risks=domain_risks,
        evidence_signals=evidence_signals,
        tech_approach="Python API with deterministic analysis.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )


def _seed_brief(store: Store) -> str:
    store.insert_signal(
        Signal(
            id="sig-risk-register-md",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Risk register markdown evidence",
            content="Implementers want source-linked risk review.",
            url="https://example.com/risk-register-md",
            tags=["risk"],
            credibility=0.8,
        )
    )
    lead = _unit(
        "bu-risk-md-lead",
        domain_risks=[
            "Framework adapters may change quickly",
            "Privacy review is required for customer workflow data",
        ],
        evidence_signals=["sig-risk-register-md"],
    )
    support = _unit(
        "bu-risk-md-support",
        domain_risks=[
            "Framework adapters may change quickly",
            "Buyer willingness to adopt the workflow is unproven",
        ],
        evidence_signals=[],
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    return store.insert_design_brief(
        ProjectBrief(
            title="Risk Register Markdown Brief",
            domain="developer-tools",
            theme="handoff-risk",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=81.0,
            why_this_now="Implementation handoffs need consolidated risk review.",
            merged_product_concept="A design brief risk register.",
            synthesis_rationale="Combines design handoff and risk review ideas.",
            mvp_scope=["Risk API", "Markdown export"],
            first_milestones=["Aggregate risks", "Expose markdown endpoint"],
            validation_plan="Compare REST JSON and Markdown outputs.",
            risks=["Dependency risk from external API churn."],
            source_idea_ids=["bu-risk-md-lead", "bu-risk-md-support"],
        )
    )


@pytest.fixture
def risk_register_markdown_client(tmp_path) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "risk_register_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        brief_id = _seed_brief(store)
    finally:
        store.close()

    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_risk_register_markdown_export_success(
    risk_register_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = risk_register_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/risk-register.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Risk-Register-Markdown-Brief-risk-register.md"'
    )
    assert response.text.startswith("# Risk Register: Risk Register Markdown Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "Risks:" in response.text
    assert "- Category: dependency" in response.text
    assert "- Severity: high" in response.text
    assert "- Mitigation:" in response.text
    assert "- Validation action:" in response.text


def test_get_design_brief_risk_register_markdown_missing_brief(
    risk_register_markdown_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = risk_register_markdown_client
    response = client.get("/api/v1/design-briefs/dbf-missing/risk-register.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"


def test_get_design_brief_risk_register_json_endpoint_unchanged(
    risk_register_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = risk_register_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/risk-register")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert any(risk["description"] == "Framework adapters may change quickly" for risk in data["risks"])
