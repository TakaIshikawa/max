"""Tests for buyer FAQ generation from design briefs."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_buyer_faq import (
    SCHEMA_VERSION,
    build_design_brief_buyer_faq,
    render_design_brief_buyer_faq,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_build_design_brief_buyer_faq_returns_structured_questions(tmp_path) -> None:
    store = Store(str(tmp_path / "buyer_faq.db"))
    try:
        brief_id = _seed_supported_brief(store)
        report = build_design_brief_buyer_faq(store, brief_id)
        repeated = build_design_brief_buyer_faq(store, brief_id)
    finally:
        store.close()

    assert report == repeated
    assert report is not None
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == "max.design_brief.buyer_faq"
    assert report["design_brief"]["id"] == brief_id
    assert report["missing_inputs"] == []
    assert [area["area"] for area in report["concern_areas"]] == [
        "problem_fit",
        "differentiation",
        "implementation_effort",
        "security_compliance",
        "pricing",
        "adoption_risk",
        "proof_points",
    ]
    assert [question["area"] for question in report["questions"]] == [
        "problem_fit",
        "differentiation",
        "implementation_effort",
        "security_compliance",
        "pricing",
        "adoption_risk",
        "proof_points",
    ]
    assert all(
        {"question", "answer", "evidence_refs", "confidence"} <= set(question)
        for question in report["questions"]
    )
    assert all(0.0 <= question["confidence"] <= 1.0 for question in report["questions"])
    evidence_ids = {
        ref["id"]
        for question in report["questions"]
        for ref in question["evidence_refs"]
    }
    assert {"sig-faq-market", "sig-faq-security", "bu-faq-lead"} <= evidence_ids
    assert any("Competitor FAQ Tool" in question["answer"] for question in report["questions"])
    assert any("$" in question["answer"] for question in report["questions"] if question["area"] == "pricing")


def test_buyer_faq_includes_missing_inputs_for_sparse_supporting_data(tmp_path) -> None:
    store = Store(str(tmp_path / "buyer_faq_sparse.db"))
    try:
        brief_id = _seed_sparse_brief(store)
        report = build_design_brief_buyer_faq(store, brief_id)
    finally:
        store.close()

    assert report is not None
    missing = [item["input"] for item in report["missing_inputs"]]
    assert missing == ["pricing_data", "competitive_data", "evidence_data"]
    assert report["summary"]["missing_input_count"] == 3
    assert report["summary"]["evidence_ref_count"] == 1
    assert report["questions"][0]["answer"]


def test_render_design_brief_buyer_faq_markdown_groups_by_concern_area(tmp_path) -> None:
    store = Store(str(tmp_path / "buyer_faq_render.db"))
    try:
        brief_id = _seed_supported_brief(store)
        report = build_design_brief_buyer_faq(store, brief_id)
    finally:
        store.close()

    assert report is not None
    markdown = render_design_brief_buyer_faq(report)

    assert markdown.startswith("# Buyer FAQ: Buyer FAQ Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{brief_id}`" in markdown
    assert "## Problem Fit" in markdown
    assert "## Differentiation" in markdown
    assert "## Implementation Effort" in markdown
    assert "## Security Or Compliance" in markdown
    assert "## Pricing" in markdown
    assert "## Adoption Risk" in markdown
    assert "## Proof Points" in markdown
    assert "sig-faq-market" in markdown
    assert "Competitor FAQ Tool" in markdown


def test_render_design_brief_buyer_faq_json_is_deterministic_and_preserves_refs(tmp_path) -> None:
    store = Store(str(tmp_path / "buyer_faq_json.db"))
    try:
        brief_id = _seed_supported_brief(store)
        report = build_design_brief_buyer_faq(store, brief_id)
    finally:
        store.close()

    assert report is not None
    rendered = render_design_brief_buyer_faq(report, fmt="json")
    assert rendered == render_design_brief_buyer_faq(report, fmt="json")
    payload = json.loads(rendered)
    assert payload == report
    refs = {ref["id"]: ref for ref in payload["evidence_refs"]}
    assert refs["sig-faq-market"]["url"] == "https://example.com/sig-faq-market"
    assert refs["sig-faq-security"]["source_type"] == "security"
    with pytest.raises(ValueError):
        render_design_brief_buyer_faq(report, fmt="yaml")


def test_build_design_brief_buyer_faq_missing_brief_returns_none(tmp_path) -> None:
    store = Store(str(tmp_path / "buyer_faq_missing.db"))
    try:
        report = build_design_brief_buyer_faq(store, "dbf-missing")
    finally:
        store.close()

    assert report is None


def _seed_supported_brief(store: Store) -> str:
    for signal in (
        _signal("sig-faq-market", SignalSourceType.SURVEY, "market"),
        _signal("sig-faq-security", SignalSourceType.SECURITY, "security"),
        _signal("sig-faq-problem", SignalSourceType.FORUM, "problem"),
    ):
        store.insert_signal(signal)
    store.insert_insight(
        Insight(
            id="ins-faq-proof",
            category=InsightCategory.EMERGING_PATTERN,
            title="FAQ buyer proof",
            summary="Buyers want concise proof and implementation answers.",
            evidence=["sig-faq-problem"],
            confidence=0.8,
            domains=["developer-tools"],
        )
    )

    lead = BuildableUnit(
        id="bu-faq-lead",
        title="Buyer FAQ Lead",
        one_liner="Sales teams need buyer-ready FAQ exports.",
        category="application",
        problem="Design briefs are too internal for buyer discovery.",
        solution="Export buyer-facing questions and concise answers.",
        value_proposition="Help sales and validation teams explain the offer consistently.",
        specific_user="solution engineer",
        buyer="VP of Sales",
        workflow_context="buyer discovery handoff",
        current_workaround="manual notes copied from design briefs",
        why_now="Validation calls need consistent buyer narrative.",
        validation_plan="Run five buyer discovery calls with the FAQ.",
        first_10_customers="developer platform sales teams",
        domain_risks=["Security review may block enterprise pilots."],
        evidence_signals=["sig-faq-market", "sig-faq-security"],
        inspiring_insights=["ins-faq-proof"],
        tech_approach="Python export module.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    store.insert_evaluation(_evaluation(lead.id))
    store.insert_prior_art_match(
        lead.id,
        {
            "source": "github",
            "title": "Competitor FAQ Tool",
            "url": "https://github.com/example/competitor-faq-tool",
            "description": "Existing FAQ generator for sales teams.",
            "relevance_score": 0.84,
            "match_signals": {"stars": 42},
            "search_query": "buyer faq generator",
        },
    )
    return store.insert_design_brief(
        ProjectBrief(
            title="Buyer FAQ Brief",
            domain="developer-tools",
            theme="buyer-narrative",
            lead=Candidate(unit=lead),
            readiness_score=88.0,
            why_this_now="Validation calls need consistent buyer narrative.",
            merged_product_concept="A deterministic buyer FAQ for persisted design briefs.",
            synthesis_rationale="Evidence links sales, validation, security, and pricing questions.",
            mvp_scope=["FAQ JSON export", "FAQ Markdown export"],
            first_milestones=["Return deterministic buyer FAQ"],
            validation_plan="Run five buyer discovery calls with the FAQ.",
            risks=["Security review may block enterprise pilots."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )


def _seed_sparse_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-faq-sparse",
        title="Sparse Buyer FAQ Lead",
        one_liner="Generate FAQs when data is sparse.",
        category="application",
        problem="Sparse briefs need buyer FAQ fallbacks.",
        solution="Use deterministic fallback answers.",
        value_proposition="Keep discovery moving while evidence is collected.",
        specific_user="",
        buyer="",
        workflow_context="",
        validation_plan="",
        domain_risks=[],
        evidence_signals=[],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Sparse Buyer FAQ Brief",
            domain="developer-tools",
            theme="buyer-narrative",
            lead=Candidate(unit=lead),
            readiness_score=52.0,
            why_this_now="The team needs a buyer narrative before discovery.",
            merged_product_concept="A sparse buyer FAQ export.",
            synthesis_rationale="Tests missing data reporting.",
            mvp_scope=[],
            first_milestones=[],
            validation_plan="",
            risks=[],
            source_idea_ids=[lead.id],
            design_status="candidate",
        )
    )


def _signal(signal_id: str, source_type: SignalSourceType, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=f"{role}-fixture",
        title=f"{role.title()} FAQ evidence",
        content=f"Evidence for {role} buyer FAQ validation.",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.75, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(value=5.0, confidence=0.7, reasoning="some alternatives"),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=84.0,
        strengths=["clear buyer"],
        weaknesses=["needs more proof"],
        recommendation="yes",
        weights_used={"addressable_scale": 0.2},
    )
