"""Tests for deterministic evaluation sensitivity reports."""

from __future__ import annotations

from max.evaluation.sensitivity import analyze_evaluation_sensitivity
from max.types.evaluation import DimensionScore, UtilityEvaluation


def _score(value: float, confidence: float = 0.8, reasoning: str = "reason") -> DimensionScore:
    return DimensionScore(value=value, confidence=confidence, reasoning=reasoning)


def _evaluation() -> UtilityEvaluation:
    return UtilityEvaluation(
        buildable_unit_id="bu-sensitive",
        pain_severity=_score(9.0, reasoning="Pain is frequent."),
        addressable_scale=_score(6.0, reasoning="Market is plausible."),
        build_effort=_score(8.0, reasoning="MVP is straightforward."),
        composability=_score(8.5, reasoning="Integrates cleanly."),
        competitive_density=_score(5.0, reasoning="Several alternatives exist."),
        timing_fit=_score(7.0, reasoning="Timing is good."),
        compounding_value=_score(4.5, reasoning="Value is mostly linear."),
        overall_score=70.5,
        strengths=["Strong workflow fit"],
        weaknesses=["Needs better market proof"],
        recommendation="yes",
        weights_used={
            "pain_severity": 0.20,
            "addressable_scale": 0.15,
            "build_effort": 0.15,
            "composability": 0.15,
            "competitive_density": 0.10,
            "timing_fit": 0.10,
            "compounding_value": 0.15,
        },
    )


def test_sensitivity_ranks_dimensions_by_absolute_score_impact() -> None:
    report = analyze_evaluation_sensitivity(_evaluation())

    impacts = [abs(item["score_delta"]) for item in report["dimensions"]]
    assert impacts == sorted(impacts, reverse=True)
    assert report["dimensions"][0]["dimension"] == "pain_severity"
    assert report["dimensions"][0]["score_delta"] < 0
    assert report["dimensions"][0]["leave_one_out_score"] == 65.62
    assert report["dimensions"][0]["recommendation_delta"] == -1


def test_sensitivity_includes_baseline_weights_and_perturbations() -> None:
    report = analyze_evaluation_sensitivity(_evaluation())
    pain = next(item for item in report["dimensions"] if item["dimension"] == "pain_severity")

    assert report["baseline_score"] == 70.5
    assert report["baseline_recommendation"] == "yes"
    assert round(sum(report["weight_profile"].values()), 6) == 1.0
    assert pain["weight_down_score"] < report["baseline_score"]
    assert pain["weight_up_score"] > report["baseline_score"]
    assert pain["weight_down_delta"] == round(pain["weight_down_score"] - 70.5, 2)
    assert pain["weight_up_delta"] == round(pain["weight_up_score"] - 70.5, 2)
    assert "Pain severity" in pain["explanation"]


def test_sensitivity_accepts_custom_weight_mapping() -> None:
    report = analyze_evaluation_sensitivity(
        _evaluation(),
        weights={
            "pain_severity": 0.10,
            "addressable_scale": 0.10,
            "build_effort": 0.10,
            "composability": 0.10,
            "competitive_density": 0.10,
            "timing_fit": 0.10,
            "compounding_value": 0.40,
        },
    )

    assert report["weight_profile"]["compounding_value"] == 0.4
    assert report["dimensions"][0]["dimension"] == "compounding_value"
    assert report["dimensions"][0]["score_delta"] > 0
