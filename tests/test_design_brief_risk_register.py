from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_risk_register import (
    SCHEMA_VERSION,
    build_design_brief_risk_register,
    render_design_brief_risk_register,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


def _unit(unit_id: str, *, domain_risks: list[str], evidence_signals: list[str]) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Risk Source {unit_id}",
        one_liner="Risk source idea",
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
            id="sig-risk-register",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Risk register evidence",
            content="Implementers want source-linked risk review.",
            url="https://example.com/risk-register",
            tags=["risk"],
            credibility=0.8,
        )
    )
    lead = _unit(
        "bu-risk-lead",
        domain_risks=[
            "Framework adapters may change quickly",
            "Privacy review is required for customer workflow data",
        ],
        evidence_signals=["sig-risk-register"],
    )
    support = _unit(
        "bu-risk-support",
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
            title="Risk Register Brief",
            domain="developer-tools",
            theme="handoff-risk",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=81.0,
            why_this_now="Implementation handoffs need consolidated risk review.",
            merged_product_concept="A design brief risk register.",
            synthesis_rationale="Combines design handoff and risk review ideas.",
            mvp_scope=["Risk API", "MCP access"],
            first_milestones=["Aggregate risks", "Expose endpoint"],
            validation_plan="Compare REST and MCP outputs.",
            risks=["Dependency risk from external API churn."],
            source_idea_ids=["bu-risk-lead", "bu-risk-support"],
        )
    )


def test_build_design_brief_risk_register_aggregates_and_dedupes(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        register = build_design_brief_risk_register(store, brief_id)
    finally:
        store.close()

    assert register is not None
    assert register["schema_version"] == SCHEMA_VERSION
    assert register["design_brief"]["id"] == brief_id
    assert register["design_brief"]["source_idea_ids"] == ["bu-risk-lead", "bu-risk-support"]

    risks = register["risks"]
    descriptions = [risk["description"] for risk in risks]
    assert descriptions.count("Framework adapters may change quickly") == 1

    adapter_risk = next(risk for risk in risks if risk["description"] == "Framework adapters may change quickly")
    assert adapter_risk["category"] == "dependency"
    assert adapter_risk["severity"] == "high"
    assert adapter_risk["likelihood"] == "possible"
    assert adapter_risk["source_idea_ids"] == ["bu-risk-lead", "bu-risk-support"]
    assert adapter_risk["mitigation"]
    assert adapter_risk["validation_action"]

    categories = {risk["category"] for risk in risks}
    assert {"market", "compliance", "dependency", "evidence"} <= categories
    assert all(risk["source_idea_ids"] is not None for risk in risks)


def test_build_design_brief_risk_register_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_risk_register(store, "dbf-missing") is None
    finally:
        store.close()


def test_render_design_brief_risk_register_json_round_trips_pretty_and_deterministic(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        register = build_design_brief_risk_register(store, brief_id)
    finally:
        store.close()

    assert register is not None
    rendered = render_design_brief_risk_register(register, "json")
    parsed = json.loads(rendered)

    assert rendered.endswith("\n")
    assert rendered.startswith('{\n  "design_brief":')
    assert parsed == register
    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["design_brief"]["id"] == brief_id
    assert [risk["id"] for risk in parsed["risks"]] == [
        "dbrr-001-compliance-privacy-review-is-required-for-custo",
        "dbrr-002-dependency-dependency-risk-from-external-api-ch",
        "dbrr-003-dependency-framework-adapters-may-change-quickl",
        "dbrr-004-market-buyer-willingness-to-adopt-the-workf",
        "dbrr-005-evidence-uneven-source-evidence",
    ]


def test_render_design_brief_risk_register_json_preserves_kind_when_present(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        register = build_design_brief_risk_register(store, brief_id)
    finally:
        store.close()

    assert register is not None
    report_with_kind = {"kind": "max.design_brief.risk_register", **register}
    parsed = json.loads(render_design_brief_risk_register(report_with_kind, "json"))

    assert parsed["kind"] == "max.design_brief.risk_register"
    assert parsed["schema_version"] == SCHEMA_VERSION


def test_render_design_brief_risk_register_markdown_unchanged(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        _brief_id = _seed_brief(store)
        register = build_design_brief_risk_register(store, _brief_id)
    finally:
        store.close()

    assert register is not None

    markdown = render_design_brief_risk_register(register, "markdown")
    assert markdown.startswith("# Risk Register: Risk Register Brief")
    assert "Schema: `max.design_brief.risk_register.v1`" in markdown
    assert "Risks: 5" in markdown
    assert "## 1. Privacy review is required for customer workflow data" in markdown
    assert "Validation action:" in markdown


def test_render_design_brief_risk_register_unsupported_format_raises(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        register = build_design_brief_risk_register(store, brief_id)
    finally:
        store.close()

    assert register is not None
    with pytest.raises(ValueError):
        render_design_brief_risk_register(register, "yaml")


@pytest.fixture
def risk_client(tmp_path):
    db_path = str(tmp_path / "api.db")
    store = Store(db_path=db_path, wal_mode=True)
    brief_id = _seed_brief(store)
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


def test_get_design_brief_risk_register_rest_response(risk_client) -> None:
    client, brief_id = risk_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/risk-register")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert any(risk["description"] == "Framework adapters may change quickly" for risk in data["risks"])


def test_get_design_brief_risk_register_rest_not_found(risk_client) -> None:
    client, _brief_id = risk_client
    response = client.get("/api/v1/design-briefs/dbf-missing/risk-register")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
