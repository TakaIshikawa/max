"""Tests for domain review threshold recommendations."""

from __future__ import annotations

from max.analysis.thresholds import (
    DEFAULT_APPROVE_THRESHOLD,
    DEFAULT_REJECT_THRESHOLD,
    recommend_review_thresholds,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(unit_id: str, domain: str) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="A test idea",
        category=BuildableCategory.APPLICATION,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain=domain,
    )


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=score,
        recommendation="yes" if score >= 68 else "no",
    )


def _reviewed(store: Store, unit_id: str, domain: str, score: float, outcome: str) -> None:
    store.insert_buildable_unit(_unit(unit_id, domain))
    store.insert_evaluation(_evaluation(unit_id, score))
    store.insert_feedback(unit_id, outcome)


def test_mixed_history_computes_domain_thresholds(store: Store) -> None:
    for idx, score in enumerate([70.0, 80.0, 90.0], 1):
        _reviewed(store, f"bu-ap-{idx}", "devtools", score, "approved")
    for idx, score in enumerate([30.0, 40.0, 50.0], 1):
        _reviewed(store, f"bu-rj-{idx}", "devtools", score, "rejected")

    [rec] = recommend_review_thresholds(store, min_samples=4)

    assert rec.domain == "devtools"
    assert rec.sample_count == 6
    assert rec.approved_count == 3
    assert rec.rejected_count == 3
    assert rec.sufficient_samples is True
    assert rec.fallback_used is False
    assert rec.approve_threshold == 75.0
    assert rec.reject_threshold == 45.0


def test_approved_only_history_uses_reject_default(store: Store) -> None:
    for idx, score in enumerate([66.0, 72.0, 84.0], 1):
        _reviewed(store, f"bu-ap-only-{idx}", "healthcare", score, "approved")

    [rec] = recommend_review_thresholds(store, min_samples=3)

    assert rec.domain == "healthcare"
    assert rec.approved_count == 3
    assert rec.rejected_count == 0
    assert rec.sufficient_samples is True
    assert rec.fallback_used is True
    assert rec.approve_threshold == 69.0
    assert rec.reject_threshold == DEFAULT_REJECT_THRESHOLD


def test_rejected_only_history_uses_approve_default(store: Store) -> None:
    for idx, score in enumerate([35.0, 45.0, 55.0], 1):
        _reviewed(store, f"bu-rj-only-{idx}", "fintech", score, "rejected")

    [rec] = recommend_review_thresholds(store, min_samples=3)

    assert rec.domain == "fintech"
    assert rec.approved_count == 0
    assert rec.rejected_count == 3
    assert rec.sufficient_samples is True
    assert rec.fallback_used is True
    assert rec.approve_threshold == DEFAULT_APPROVE_THRESHOLD
    assert rec.reject_threshold == 50.0


def test_insufficient_samples_fall_back_to_defaults(store: Store) -> None:
    _reviewed(store, "bu-one", "legaltech", 88.0, "approved")

    [rec] = recommend_review_thresholds(store, min_samples=2)

    assert rec.domain == "legaltech"
    assert rec.sample_count == 1
    assert rec.sufficient_samples is False
    assert rec.fallback_used is True
    assert rec.approve_threshold == DEFAULT_APPROVE_THRESHOLD
    assert rec.reject_threshold == DEFAULT_REJECT_THRESHOLD


def test_latest_feedback_outcome_wins(store: Store) -> None:
    _reviewed(store, "bu-flip", "devtools", 82.0, "approved")
    store.insert_feedback("bu-flip", "rejected", "changed mind")

    [rec] = recommend_review_thresholds(store, domain="devtools", min_samples=1)

    assert rec.approved_count == 0
    assert rec.rejected_count == 1
    assert rec.approve_threshold == DEFAULT_APPROVE_THRESHOLD
    assert rec.reject_threshold == 82.0


def test_domain_filter_without_samples_returns_default_recommendation(store: Store) -> None:
    [rec] = recommend_review_thresholds(store, domain="missing", min_samples=3)

    assert rec.domain == "missing"
    assert rec.sample_count == 0
    assert rec.sufficient_samples is False
    assert rec.approve_threshold == DEFAULT_APPROVE_THRESHOLD
    assert rec.reject_threshold == DEFAULT_REJECT_THRESHOLD
