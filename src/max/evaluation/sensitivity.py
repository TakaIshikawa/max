"""Sensitivity analysis for deterministic utility evaluations."""

from __future__ import annotations

from typing import Any

from max.evaluation.explain import DIMENSION_LABELS
from max.evaluation.weights import DEFAULT_WEIGHTS, compute_overall_score
from max.types.evaluation import DimensionScore, UtilityEvaluation


RECOMMENDATION_ORDER: dict[str, int] = {
    "strong_no": 0,
    "no": 1,
    "maybe": 2,
    "yes": 3,
    "strong_yes": 4,
}


def analyze_evaluation_sensitivity(
    evaluation: UtilityEvaluation,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Rank score dimensions by their impact on the recommendation.

    The primary impact is the leave-one-dimension-out score delta. Each row also
    includes +/-10% weight perturbations with weights renormalized to sum to 1.0.
    """
    weight_profile = _effective_weights(evaluation, weights)
    dimension_values = _dimension_values(evaluation)
    baseline_score = compute_overall_score(dimension_values, weight_profile)
    baseline_recommendation = _recommendation_for_score(
        baseline_score,
        fallback=evaluation.recommendation,
    )

    dimensions = [
        _dimension_impact(
            dimension,
            evaluation,
            dimension_values,
            weight_profile,
            baseline_score,
            baseline_recommendation,
        )
        for dimension in DEFAULT_WEIGHTS
    ]
    dimensions.sort(
        key=lambda item: (
            abs(item["score_delta"]),
            abs(item["recommendation_delta"]),
            item["weight"],
            item["dimension"],
        ),
        reverse=True,
    )

    return {
        "baseline_score": baseline_score,
        "baseline_recommendation": baseline_recommendation,
        "weight_profile": weight_profile,
        "dimensions": dimensions,
    }


def _dimension_impact(
    dimension: str,
    evaluation: UtilityEvaluation,
    dimension_values: dict[str, float],
    weights: dict[str, float],
    baseline_score: float,
    baseline_recommendation: str,
) -> dict[str, Any]:
    without_weights = _renormalize(
        {name: weight for name, weight in weights.items() if name != dimension}
    )
    without_values = {
        name: value for name, value in dimension_values.items() if name != dimension
    }
    without_score = compute_overall_score(without_values, without_weights)
    without_recommendation = _recommendation_for_score(without_score)
    score_delta = round(without_score - baseline_score, 2)
    recommendation_delta = _recommendation_delta(without_recommendation, baseline_recommendation)

    weight_down = _perturbed_weights(weights, dimension, 0.90)
    weight_up = _perturbed_weights(weights, dimension, 1.10)
    down_score = compute_overall_score(dimension_values, weight_down)
    up_score = compute_overall_score(dimension_values, weight_up)
    down_recommendation = _recommendation_for_score(down_score)
    up_recommendation = _recommendation_for_score(up_score)

    score: DimensionScore = getattr(evaluation, dimension)
    return {
        "dimension": dimension,
        "label": DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title()),
        "score": score.value,
        "confidence": score.confidence,
        "weight": weights[dimension],
        "score_delta": score_delta,
        "recommendation_delta": recommendation_delta,
        "leave_one_out_score": without_score,
        "leave_one_out_recommendation": without_recommendation,
        "weight_down_score": down_score,
        "weight_down_delta": round(down_score - baseline_score, 2),
        "weight_down_recommendation": down_recommendation,
        "weight_up_score": up_score,
        "weight_up_delta": round(up_score - baseline_score, 2),
        "weight_up_recommendation": up_recommendation,
        "explanation": _impact_explanation(
            dimension,
            score.value,
            weights[dimension],
            score_delta,
            recommendation_delta,
        ),
    }


def _effective_weights(
    evaluation: UtilityEvaluation,
    override: dict[str, float] | None,
) -> dict[str, float]:
    candidate = override if override is not None else evaluation.weights_used
    merged = dict(DEFAULT_WEIGHTS)
    merged.update(
        {
            dimension: float(weight)
            for dimension, weight in (candidate or {}).items()
            if dimension in DEFAULT_WEIGHTS and weight > 0
        }
    )
    return _renormalize(merged)


def _dimension_values(evaluation: UtilityEvaluation) -> dict[str, float]:
    return {
        dimension: float(getattr(evaluation, dimension).value)
        for dimension in DEFAULT_WEIGHTS
    }


def _renormalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weight for weight in weights.values() if weight > 0)
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    normalized = {
        dimension: round(weight / total, 6)
        for dimension, weight in weights.items()
        if weight > 0
    }
    drift = round(1.0 - sum(normalized.values()), 6)
    if drift and normalized:
        first = next(iter(normalized))
        normalized[first] = round(normalized[first] + drift, 6)
    return normalized


def _perturbed_weights(
    weights: dict[str, float],
    dimension: str,
    multiplier: float,
) -> dict[str, float]:
    perturbed = dict(weights)
    perturbed[dimension] = perturbed[dimension] * multiplier
    return _renormalize(perturbed)


def _recommendation_for_score(score: float, *, fallback: str | None = None) -> str:
    if fallback in RECOMMENDATION_ORDER and 50.0 <= score < 85.0:
        # Preserve model nuance around the broad middle band unless the score
        # crosses the deterministic strong/negative thresholds.
        if fallback in {"maybe", "yes"}:
            return fallback
    if score >= 85.0:
        return "strong_yes"
    if score >= 70.0:
        return "yes"
    if score >= 50.0:
        return "maybe"
    if score >= 35.0:
        return "no"
    return "strong_no"


def _recommendation_delta(current: str, baseline: str) -> int:
    return RECOMMENDATION_ORDER[current] - RECOMMENDATION_ORDER[baseline]


def _impact_explanation(
    dimension: str,
    score: float,
    weight: float,
    score_delta: float,
    recommendation_delta: int,
) -> str:
    label = DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title())
    direction = "increase" if score_delta > 0 else "decrease" if score_delta < 0 else "not change"
    rec_phrase = (
        " and changes the recommendation"
        if recommendation_delta
        else " without changing the recommendation"
    )
    return (
        f"Removing {label} would {direction} the score by "
        f"{abs(score_delta):.2f} points{rec_phrase}; it currently scores "
        f"{score:.1f}/10 at weight {weight:.2f}."
    )
