"""Tests for evaluation calibration reporting."""

from __future__ import annotations

import pytest

from max.analysis.evaluation_calibration import build_evaluation_calibration_report
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(unit_id: str, domain: str = "devtools") -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="A calibration test idea",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain=domain,
    )


def _score(value: float = 7.0) -> DimensionScore:
    return DimensionScore(value=value, confidence=0.7, reasoning="test")


def _evaluation(unit_id: str, score: float, recommendation: str) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(6.0),
        composability=_score(7.0),
        competitive_density=_score(8.0),
        timing_fit=_score(7.0),
        compounding_value=_score(6.0),
        overall_score=score,
        recommendation=recommendation,
        weights_used={"pain_severity": 0.20},
    )


def _seed(
    store: Store,
    unit_id: str,
    *,
    domain: str,
    score: float,
    recommendation: str,
    outcome: str,
) -> None:
    store.insert_buildable_unit(_unit(unit_id, domain))
    store.insert_evaluation(_evaluation(unit_id, score, recommendation))
    store.insert_feedback(unit_id, outcome)


def test_calibration_groups_by_domain_and_recommendation(store: Store) -> None:
    _seed(store, "bu-cal-1", domain="devtools", score=92.0, recommendation="yes", outcome="approved")
    _seed(store, "bu-cal-2", domain="devtools", score=88.0, recommendation="yes", outcome="rejected")
    _seed(store, "bu-cal-3", domain="devtools", score=42.0, recommendation="yes", outcome="approved")
    _seed(store, "bu-cal-4", domain="legaltech", score=72.0, recommendation="maybe", outcome="published")

    report = build_evaluation_calibration_report(store)

    assert report.total_groups == 2
    group = next(g for g in report.groups if g.domain == "devtools" and g.recommendation == "yes")
    assert group.sample_count == 3
    assert group.approved_count == 2
    assert group.rejected_count == 1
    assert group.approval_rate == pytest.approx(0.6667)
    assert group.rejection_rate == pytest.approx(0.3333)
    assert group.average_overall_score == pytest.approx(74.0)
    assert group.high_score_sample_count == 2
    assert group.high_score_rejection_count == 1
    assert group.high_score_rejection_rate == pytest.approx(0.5)
    assert group.low_score_sample_count == 1
    assert group.low_score_approval_count == 1
    assert group.low_score_approval_rate == pytest.approx(1.0)
    assert [(b.min_score, b.sample_count) for b in group.score_buckets] == [
        (40.0, 1),
        (80.0, 2),
    ]


def test_calibration_uses_latest_feedback_only(store: Store) -> None:
    store.insert_buildable_unit(_unit("bu-cal-latest", "devtools"))
    store.insert_evaluation(_evaluation("bu-cal-latest", 86.0, "yes"))
    store.insert_feedback("bu-cal-latest", "approved")
    store.insert_feedback("bu-cal-latest", "rejected")

    report = build_evaluation_calibration_report(store)

    group = report.groups[0]
    assert group.sample_count == 1
    assert group.approved_count == 0
    assert group.rejected_count == 1
    assert group.high_score_rejection_rate == 1.0


def test_calibration_domain_min_samples_and_limit(store: Store) -> None:
    _seed(store, "bu-cal-d1", domain="devtools", score=91.0, recommendation="yes", outcome="approved")
    _seed(store, "bu-cal-d2", domain="devtools", score=68.0, recommendation="maybe", outcome="rejected")
    _seed(store, "bu-cal-l1", domain="legaltech", score=79.0, recommendation="yes", outcome="approved")

    report = build_evaluation_calibration_report(
        store,
        domain="devtools",
        min_samples=1,
        limit=1,
    )

    assert report.domain == "devtools"
    assert report.total_groups == 2
    assert len(report.groups) == 1
    assert {group.domain for group in report.groups} == {"devtools"}

    empty = build_evaluation_calibration_report(store, domain="devtools", min_samples=2)
    assert empty.total_groups == 0
    assert empty.groups == []
