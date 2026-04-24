from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_competitive_landscape import (
    SCHEMA_VERSION,
    build_design_brief_competitive_landscape,
    render_design_brief_competitive_landscape,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(unit_id: str, *, title: str, problem: str, solution: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="Competitive landscape source idea",
        category="application",
        problem=problem,
        solution=solution,
        value_proposition="Give platform teams a clearer deployment decision.",
        specific_user="platform engineer",
        buyer="developer platform lead",
        workflow_context="pre-release agent deployment review",
        current_workaround="manual reviews and scattered spreadsheets",
        why_now="Agent deployments need repeatable review gates.",
        validation_plan="Run five buyer interviews and a smoke test.",
        first_10_customers="platform teams deploying AI agents",
        domain_risks=["Incumbent governance tools may expand into the workflow."],
        tech_approach="Python API with deterministic reporting",
        suggested_stack={"language": "python", "framework": "fastapi"},
        evidence_signals=["sig-competitive"],
        domain="agent-tools",
        status="approved",
    )


def _evaluation(unit_id: str, density: float) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(
            value=density,
            confidence=0.8,
            reasoning="Stored competitors create positioning pressure.",
        ),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=78.0,
        strengths=["Clear buyer"],
        weaknesses=["Crowded deployment review category"],
        recommendation="yes",
        weights_used={"competitive_density": 0.1},
    )


def _seed_brief(store: Store, *, with_prior_art: bool = True) -> str:
    lead = _unit(
        "bu-comp-lead",
        title="Agent Release Gate",
        problem="Platform teams cannot compare agent release risk before deployment.",
        solution="Score agent releases against policy, evidence, and prior incidents.",
    )
    support = _unit(
        "bu-comp-support",
        title="Agent Policy Review",
        problem="Platform teams need repeatable policy review before agent deployment.",
        solution="Generate deployment readiness reports for platform engineers.",
    )
    nearby = _unit(
        "bu-comp-nearby",
        title="Agent Deployment Review",
        problem="Platform teams cannot compare agent release risk before launch.",
        solution="Review agent deployment readiness for platform engineers.",
    )
    store.insert_buildable_unit(lead)
    store.insert_buildable_unit(support)
    store.insert_buildable_unit(nearby)
    store.insert_evaluation(_evaluation(lead.id, 4.5))
    store.insert_evaluation(_evaluation(support.id, 6.5))

    if with_prior_art:
        store.insert_prior_art_match(
            lead.id,
            {
                "source": "github",
                "title": "open-agent-gate",
                "url": "https://github.com/example/open-agent-gate",
                "description": "Open-source release gate for agent deployment policy.",
                "relevance_score": 0.91,
                "match_signals": {"stars": 220},
                "search_query": "agent release gate",
            },
        )
        store.insert_prior_art_match(
            support.id,
            {
                "source": "product_hunt",
                "title": "AgentGuard Launch Review",
                "url": "https://www.producthunt.com/products/agentguard",
                "description": "Productized launch review workflow for AI agent teams.",
                "relevance_score": 0.74,
                "match_signals": {"votes": 88},
                "search_query": "agent launch review",
            },
        )
        store.update_prior_art_status(lead.id, "strong_match")
        store.update_prior_art_status(support.id, "weak_match")

    return store.insert_design_brief(
        ProjectBrief(
            title="Agent Release Gate Brief",
            domain="agent-tools",
            theme="release-governance",
            lead=Candidate(unit=lead),
            supporting=[Candidate(unit=support)],
            readiness_score=82.0,
            why_this_now="Agent deployments need repeatable release governance.",
            merged_product_concept="A release gate for agent deployment reviews.",
            synthesis_rationale="Combines policy review and launch readiness ideas.",
            mvp_scope=["Policy evidence report", "Deployment readiness score"],
            first_milestones=["Generate competitive landscape report"],
            validation_plan="Run buyer interviews with platform leads.",
            risks=["Competition from governance platforms is likely."],
            source_idea_ids=[lead.id, support.id],
        )
    )


def test_competitive_landscape_uses_stored_prior_art_and_positioning(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        report = build_design_brief_competitive_landscape(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["status"] == "ready"
    assert report["summary"]["prior_art_record_count"] == 2
    assert report["summary"]["competitor_cluster_count"] == 2
    assert report["saturation"]["level"] in {"medium", "high"}
    assert [cluster["source"] for cluster in report["competitor_clusters"]] == [
        "github",
        "product_hunt",
    ]
    assert report["competitor_clusters"][0]["top_competitors"][0]["title"] == "open-agent-gate"
    assert any(angle["id"] == "competitive-density-mitigation" for angle in report["differentiation_angles"])
    assert "platform engineer" in report["recommended_positioning"]
    assert report["signals"]["evaluations"][0]["competitive_density_score"] == 4.5
    assert report["signals"]["similar_ideas"]


def test_competitive_landscape_without_prior_art_is_explicit_insufficient_data(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store, with_prior_art=False)
        report = build_design_brief_competitive_landscape(store, brief_id)
    finally:
        store.close()

    assert report is not None
    assert report["status"] == "insufficient_data"
    assert report["summary"]["prior_art_record_count"] == 0
    assert report["summary"]["insufficient_data_reasons"] == [
        "No stored prior-art records are linked to the design brief source ideas."
    ]
    assert report["competitor_clusters"] == []
    assert report["saturation"]["level"] == "unknown"
    assert report["recommended_positioning"].startswith("Insufficient stored prior-art data")


def test_competitive_landscape_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        assert build_design_brief_competitive_landscape(store, "dbf-missing") is None
    finally:
        store.close()


def test_render_competitive_landscape_json_and_markdown(tmp_path) -> None:
    store = Store(str(tmp_path / "max.db"))
    try:
        brief_id = _seed_brief(store)
        report = build_design_brief_competitive_landscape(store, brief_id)
    finally:
        store.close()

    assert report is not None
    parsed = json.loads(render_design_brief_competitive_landscape(report, "json"))
    assert parsed["schema_version"] == SCHEMA_VERSION

    markdown = render_design_brief_competitive_landscape(report, "markdown")
    assert markdown.startswith("# Competitive Landscape: Agent Release Gate Brief")
    assert "Schema: `max.design_brief.competitive_landscape.v1`" in markdown
    assert "## Recommended Positioning" in markdown

    with pytest.raises(ValueError):
        render_design_brief_competitive_landscape(report, "yaml")
