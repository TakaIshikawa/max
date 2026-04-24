"""Tests for concise idea product brief export."""

from __future__ import annotations

from max.analysis.idea_product_brief_export import generate_idea_product_brief
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


def test_product_brief_markdown_contains_stable_sections_and_idea_content(tmp_path) -> None:
    db_path = str(tmp_path / "brief.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        _seed_store(store, with_evaluation=True, with_validation=True)
        unit = store.get_buildable_unit("bu-brief001")
        assert unit is not None

        brief = generate_idea_product_brief(unit, store.get_evaluation(unit.id), store)

    markdown = brief["markdown"]
    assert markdown.startswith("# Brief Idea Product Brief")
    for heading in [
        "## Problem",
        "## Target User and Buyer",
        "## Current Workaround",
        "## Solution",
        "## Why Now",
        "## Evidence",
        "## Evaluation",
        "## Risks",
        "## Validation Plan",
        "## First Milestones",
    ]:
        assert heading in markdown
    assert "Manual review queues hide duplicate handoff work." in markdown
    assert "product ops lead" in markdown
    assert "Utility score: 84.0" in markdown
    assert brief["source_ids"]["idea_ids"] == ["bu-brief001", "bu-source001"]
    assert brief["source_ids"]["evaluation_ids"] == ["bu-brief001"]


def test_product_brief_handles_missing_evaluation(tmp_path) -> None:
    db_path = str(tmp_path / "brief.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        _seed_store(store, with_evaluation=False)
        unit = store.get_buildable_unit("bu-brief001")
        assert unit is not None

        brief = generate_idea_product_brief(unit, store.get_evaluation(unit.id), store)

    assert "Utility evaluation: missing." in brief["markdown"]
    assert brief["source_ids"]["evaluation_ids"] == []
    assert "Review gate:" in brief["markdown"]


def test_product_brief_evidence_flag_controls_evidence_section(tmp_path) -> None:
    db_path = str(tmp_path / "brief.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        _seed_store(store, with_evaluation=True)
        unit = store.get_buildable_unit("bu-brief001")
        assert unit is not None

        included = generate_idea_product_brief(
            unit,
            store.get_evaluation(unit.id),
            store,
            include_evidence=True,
        )
        excluded = generate_idea_product_brief(
            unit,
            store.get_evaluation(unit.id),
            store,
            include_evidence=False,
        )

    assert "## Evidence" in included["markdown"]
    assert "sig-brief001" in included["markdown"]
    assert included["source_ids"]["signal_ids"] == ["sig-brief001"]
    assert "## Evidence" not in excluded["markdown"]
    assert excluded["source_ids"]["signal_ids"] == []


def test_product_brief_validation_flag_controls_validation_section(tmp_path) -> None:
    db_path = str(tmp_path / "brief.db")
    with Store(db_path=db_path, wal_mode=True) as store:
        _seed_store(store, with_evaluation=True, with_validation=True)
        unit = store.get_buildable_unit("bu-brief001")
        assert unit is not None

        included = generate_idea_product_brief(
            unit,
            store.get_evaluation(unit.id),
            store,
            include_validation=True,
        )
        excluded = generate_idea_product_brief(
            unit,
            store.get_evaluation(unit.id),
            store,
            include_validation=False,
        )

    assert "## Validation Plan" in included["markdown"]
    assert "Run five concierge brief reviews." in included["markdown"]
    assert len(included["source_ids"]["validation_experiment_ids"]) == 1
    assert "## Validation Plan" not in excluded["markdown"]
    assert excluded["source_ids"]["validation_experiment_ids"] == []


def _seed_store(
    store: Store,
    *,
    with_evaluation: bool,
    with_validation: bool = False,
) -> None:
    store.insert_signal(
        Signal(
            id="sig-brief001",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="Brief signal",
            content="Reviewers want a compact artifact before full specs.",
            url="https://example.com/brief",
            credibility=0.82,
        )
    )
    store.insert_insight(
        Insight(
            id="ins-brief001",
            category=InsightCategory.GAP,
            title="Brief insight",
            summary="Product reviewers need a smaller artifact before implementation specs.",
            evidence=["sig-brief001"],
            confidence=0.8,
            domains=["testing"],
        )
    )
    store.insert_buildable_unit(_brief_unit())
    if with_evaluation:
        store.insert_evaluation(_brief_evaluation())
    if with_validation:
        store.create_validation_experiment(
            "bu-brief001",
            hypothesis="Reviewers can approve the brief faster than a spec bundle.",
            method="Concierge review",
            target_sample_size=5,
            success_metric="4 of 5 reviewers can make a product decision",
            status="planned",
            result_summary="",
            evidence_urls=["https://example.com/validation"],
            confidence_delta=0.1,
        )


def _brief_unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-brief001",
        title="Brief Idea",
        one_liner="A compact product-review brief for ideas",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Manual review queues hide duplicate handoff work.",
        solution="Generate a compact Markdown brief from idea, evidence, and evaluation data.",
        target_users="humans",
        value_proposition="Reviewers can decide whether an idea deserves full spec generation.",
        specific_user="product ops lead",
        buyer="product leadership",
        workflow_context="idea triage",
        current_workaround="Reading raw idea JSON and separate endpoint outputs.",
        why_now="Spec bundles are heavier than early product review needs.",
        validation_plan="Run five concierge brief reviews.",
        first_10_customers="internal product reviewers",
        domain_risks=["Briefs may omit technical nuance."],
        evidence_rationale="Evidence shows reviewers need a smaller artifact.",
        inspiring_insights=["ins-brief001"],
        evidence_signals=["sig-brief001"],
        source_idea_ids=["bu-source001"],
        tech_approach="Compose deterministic Markdown from existing stored fields.",
        suggested_stack={"api": "fastapi", "format": "markdown"},
        composability_notes="No new persistence required.",
        quality_score=88.0,
        novelty_score=72.0,
        usefulness_score=90.0,
        prior_art_status="clear",
    )


def _brief_evaluation() -> UtilityEvaluation:
    score = DimensionScore(value=8.0, confidence=0.8, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id="bu-brief001",
        pain_severity=score,
        addressable_scale=score,
        build_effort=score,
        composability=score,
        competitive_density=score,
        timing_fit=score,
        compounding_value=score,
        overall_score=84.0,
        strengths=["Clear handoff gap"],
        weaknesses=["Needs reviewer calibration"],
        recommendation="yes",
        weights_used={"pain_severity": 0.2},
    )
