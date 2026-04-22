"""Tests for ROI forecast analysis."""

from __future__ import annotations

from max.analysis.roi_forecast import generate_roi_forecast
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _unit(
    unit_id: str,
    *,
    title: str,
    evidence: list[str],
    category: str = BuildableCategory.CLI_TOOL,
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=title,
        one_liner="A forecast test idea",
        category=category,
        ideation_mode=IdeationMode.DIRECT,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        inspiring_insights=evidence[:1],
        evidence_signals=evidence[1:],
    )


def _score(value: float, confidence: float = 0.8) -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning="test")


def _evaluation(unit_id: str, *, overall: float, effort: float) -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(effort),
        composability=_score(8.0),
        competitive_density=_score(7.0),
        timing_fit=_score(7.0),
        compounding_value=_score(6.0),
        overall_score=overall,
        recommendation="yes",
        weights_used={"pain_severity": 0.20},
    )


def test_generate_roi_forecast_ranks_by_utility_evidence_and_effort() -> None:
    easy = _unit("bu-easy", title="Easy win", evidence=["ins-1", "sig-1", "sig-2"])
    hard = _unit("bu-hard", title="Hard build", evidence=["ins-2"])

    report = generate_roi_forecast(
        [hard, easy],
        {
            "bu-easy": _evaluation("bu-easy", overall=82.0, effort=9.0),
            "bu-hard": _evaluation("bu-hard", overall=82.0, effort=2.0),
        },
    )

    assert report.total_units == 2
    assert report.evaluated_units == 2
    assert [item.idea_id for item in report.results] == ["bu-easy", "bu-hard"]
    assert report.results[0].rank == 1
    assert report.results[0].evidence_count == 3
    assert report.results[0].estimated_complexity < report.results[1].estimated_complexity


def test_generate_roi_forecast_handles_unevaluated_units() -> None:
    unit = _unit("bu-raw", title="Raw idea", evidence=[])
    unit.quality_score = 7.0

    report = generate_roi_forecast([unit], {})

    item = report.results[0]
    assert item.evaluation_score is None
    assert item.weighted_utility_score == 70.0
    assert item.warnings
