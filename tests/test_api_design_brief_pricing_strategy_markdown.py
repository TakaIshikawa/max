"""API tests for design brief pricing strategy exports."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.design_brief_pricing_strategy import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=79.0,
        strengths=["clear commercialization path"],
        weaknesses=["price needs validation"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )


@pytest.fixture
def pricing_strategy_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "pricing_strategy_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        signal = Signal(
            id="sig-pricing-api-survey",
            source_type=SignalSourceType.SURVEY,
            source_adapter="survey-fixture",
            title="Pricing API demand",
            content="Buyers need paid pilot package clarity.",
            url="https://example.com/pricing-api-demand",
            tags=["market"],
            credibility=0.8,
            metadata={"signal_role": "market"},
        )
        store.insert_signal(signal)
        lead = BuildableUnit(
            id="bu-pricing-api-lead",
            title="Pricing Strategy API Lead",
            one_liner="Expose pricing strategy artifacts",
            category="application",
            problem="Design brief consumers need pricing strategy before commercialization.",
            solution="Render pricing strategy as JSON and Markdown.",
            value_proposition="Give product leads package and price-band hypotheses.",
            specific_user="product operations lead",
            buyer="VP of Product",
            workflow_context="launch readiness review",
            validation_plan="Inspect generated pricing strategy with buyers.",
            evidence_signals=[signal.id],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_evaluation(_evaluation(lead.id))
        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Pricing Strategy Markdown Brief",
                domain="developer-tools",
                theme="pricing-export",
                lead=Candidate(unit=lead),
                readiness_score=80.0,
                why_this_now="Design brief artifacts now cover launch and product but not pricing.",
                merged_product_concept="A deterministic pricing strategy export for persisted briefs.",
                synthesis_rationale="Pricing strategy closes commercialization planning.",
                mvp_scope=["Pricing strategy endpoint", "Markdown export"],
                first_milestones=["Return Markdown through the API"],
                validation_plan="Call the endpoint and validate attachment headers.",
                risks=["Price bands need buyer validation."],
                source_idea_ids=[lead.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def pricing_strategy_client(pricing_strategy_db: tuple[str, str]) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = pricing_strategy_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_pricing_strategy_json_success(
    pricing_strategy_client: tuple[TestClient, str],
) -> None:
    client, brief_id = pricing_strategy_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/pricing-strategy")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["design_brief"]["id"] == brief_id
    assert data["packages"]
    assert data["price_bands"]
    assert data["value_metric"]
    assert data["objections"]
    assert data["validation_questions"]
    assert data["confidence"]["level"] in {"low", "medium", "high"}
    assert data["evidence_references"][0]["id"] == "sig-pricing-api-survey"


def test_get_design_brief_pricing_strategy_markdown_success(
    pricing_strategy_client: tuple[TestClient, str],
) -> None:
    client, brief_id = pricing_strategy_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/pricing-strategy.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-pricing-strategy.md"'
    )
    assert response.text.startswith("# Pricing Strategy: Pricing Strategy Markdown Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in response.text
    assert "## Recommended Packaging" in response.text
    assert "## Initial Price Bands" in response.text
    assert "## Value Metric" in response.text
    assert "## Buyer Objections" in response.text
    assert "sig-pricing-api-survey" in response.text


def test_get_design_brief_pricing_strategy_missing_brief(
    pricing_strategy_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = pricing_strategy_client

    json_response = client.get("/api/v1/design-briefs/dbf-missing/pricing-strategy")
    assert json_response.status_code == 404
    assert json_response.json()["detail"] == "Design brief not found: dbf-missing"

    markdown_response = client.get("/api/v1/design-briefs/dbf-missing/pricing-strategy.md")
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"] == "Design brief not found: dbf-missing"
