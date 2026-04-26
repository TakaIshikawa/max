"""API tests for design brief market-sizing Markdown export."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.app import create_app
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
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
        overall_score=76.0,
        strengths=["clear segment"],
        weaknesses=["needs more market evidence"],
        recommendation="yes",
        weights_used={"addressable_scale": 0.2},
    )


@pytest.fixture
def market_sizing_markdown_db(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "market_sizing_markdown_api.db")
    store = Store(db_path=db_path, wal_mode=True)
    try:
        survey = Signal(
            id="sig-market-md-survey",
            source_type=SignalSourceType.SURVEY,
            source_adapter="survey-fixture",
            title="Survey demand",
            content="Teams report recurring budget review pain.",
            url="https://example.com/survey-demand",
            tags=["market"],
            credibility=0.8,
            metadata={"signal_role": "market"},
        )
        funding = Signal(
            id="sig-market-md-funding",
            source_type=SignalSourceType.FUNDING,
            source_adapter="funding-fixture",
            title="Funding demand",
            content="Budget-owner tooling attracts funding.",
            url="https://example.com/funding-demand",
            tags=["budget"],
            credibility=0.7,
            metadata={"signal_role": "market"},
        )
        for signal in (survey, funding):
            store.insert_signal(signal)

        store.insert_insight(
            Insight(
                id="ins-market-md-demand",
                category=InsightCategory.GAP,
                title="Market sizing handoff gap",
                summary="API consumers need readable market-sizing exports.",
                evidence=[survey.id, funding.id],
                confidence=0.8,
                domains=["developer-tools"],
            )
        )

        lead = BuildableUnit(
            id="bu-market-md-lead",
            title="Market Sizing Markdown Lead",
            one_liner="Export design brief market sizing as Markdown",
            category="application",
            problem="API consumers need readable market-sizing reports.",
            solution="Render the persisted market-sizing report as Markdown.",
            value_proposition="Give budget owners a deterministic validation artifact.",
            specific_user="product operations lead",
            buyer="VP of Product",
            workflow_context="quarterly roadmap investment review",
            validation_plan="Review Markdown with budget owners.",
            inspiring_insights=["ins-market-md-demand"],
            evidence_signals=[survey.id],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_evaluation(_evaluation(lead.id))

        brief_id = store.insert_design_brief(
            ProjectBrief(
                title="Market Sizing Markdown: Pilot/Teams?",
                domain="developer-tools",
                theme="market-export",
                lead=Candidate(unit=lead),
                readiness_score=81.0,
                why_this_now="API consumers already receive JSON market sizing.",
                merged_product_concept="A Markdown market-sizing export for persisted design briefs.",
                synthesis_rationale="Completes market-sizing parity for REST clients.",
                mvp_scope=["Market-sizing Markdown endpoint"],
                first_milestones=["Return Markdown through the API"],
                validation_plan="Call the REST endpoint and inspect the attachment.",
                risks=["Market evidence may remain sparse."],
                source_idea_ids=[lead.id],
            )
        )
    finally:
        store.close()
    return db_path, brief_id


@pytest.fixture
def market_sizing_markdown_client(
    market_sizing_markdown_db: tuple[str, str],
) -> tuple[TestClient, str]:
    from max.server.dependencies import get_store

    db_path, brief_id = market_sizing_markdown_db
    app = create_app()

    def override_get_store():
        store = Store(db_path=db_path, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app), brief_id


def test_get_design_brief_market_sizing_markdown_export_success(
    market_sizing_markdown_client: tuple[TestClient, str],
) -> None:
    client, brief_id = market_sizing_markdown_client
    response = client.get(f"/api/v1/design-briefs/{brief_id}/market-sizing.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == (
        f'attachment; filename="{brief_id}-Market-Sizing-Markdown-Pilot-Teams-market-sizing.md"'
    )
    assert response.text.startswith("# Market Sizing: Market Sizing Markdown: Pilot/Teams?")
    assert "- **Confidence**:" in response.text
    for section in [
        "## Signal Counts",
        "## Market Hypotheses",
        "## Segments",
        "## Gaps",
        "## Recommended Next Validation Data",
    ]:
        assert section in response.text
    assert "survey=1" in response.text
    assert "funding=1" in response.text
    assert "bu-market-md-lead" in response.text


def test_get_design_brief_market_sizing_markdown_missing_brief(
    market_sizing_markdown_client: tuple[TestClient, str],
) -> None:
    client, _brief_id = market_sizing_markdown_client
    response = client.get("/api/v1/design-briefs/dbf-missing/market-sizing.md")

    assert response.status_code == 404
    assert response.json()["detail"] == "Design brief not found: dbf-missing"
