"""Rough return-on-effort forecasting for buildable ideas."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping

from max.evaluation.weights import DEFAULT_WEIGHTS, get_weights
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import UtilityEvaluation

DIMENSIONS = tuple(DEFAULT_WEIGHTS.keys())


@dataclass(frozen=True)
class RoiForecastItem:
    rank: int
    idea_id: str
    title: str
    domain: str
    status: str
    category: str
    roi_score: float
    evaluation_score: float | None
    weighted_utility_score: float
    evidence_count: int
    evidence_score: float
    estimated_complexity: float
    complexity_score: float
    confidence: float
    recommendation: str | None
    drivers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoiForecastReport:
    generated_at: str
    profile: str | None
    weight_profile: str
    weights: dict[str, float]
    total_units: int
    evaluated_units: int
    results: list[RoiForecastItem]


def generate_roi_forecast(
    units: list[BuildableUnit],
    evaluations: Mapping[str, UtilityEvaluation | None],
    profile: Any = None,
) -> RoiForecastReport:
    """Rank units by rough expected return per implementation effort.

    The score is intentionally deterministic and transparent: profile-weighted
    evaluation utility contributes most of the score, direct evidence volume
    adds confidence, and estimated implementation complexity discounts ideas
    that look expensive to build.
    """
    profile_name, weight_profile, weights = _resolve_profile_weights(profile)
    items = [
        _forecast_item(unit, evaluations.get(unit.id), weights)
        for unit in units
    ]
    items.sort(
        key=lambda item: (
            -item.roi_score,
            -(item.evaluation_score or 0.0),
            -item.evidence_count,
            item.title.lower(),
        )
    )
    ranked = [replace(item, rank=index) for index, item in enumerate(items, 1)]
    return RoiForecastReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        profile=profile_name,
        weight_profile=weight_profile,
        weights=weights,
        total_units=len(units),
        evaluated_units=sum(1 for unit in units if evaluations.get(unit.id) is not None),
        results=ranked,
    )


def _forecast_item(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    weights: dict[str, float],
) -> RoiForecastItem:
    evidence_count = _evidence_count(unit)
    evidence_score = round(min(evidence_count / 5.0, 1.0) * 100, 1)
    estimated_complexity = _estimated_complexity(unit, evaluation)
    complexity_score = round(max(0.0, min(100.0, (10.0 - estimated_complexity) * 10.0)), 1)
    weighted_utility_score = _weighted_utility_score(unit, evaluation, weights)
    confidence = _confidence(evaluation, evidence_count)

    roi_score = round(
        weighted_utility_score * 0.55
        + evidence_score * 0.20
        + complexity_score * 0.25,
        1,
    )

    return RoiForecastItem(
        rank=0,
        idea_id=unit.id,
        title=unit.title,
        domain=unit.domain,
        status=unit.status,
        category=str(unit.category),
        roi_score=roi_score,
        evaluation_score=evaluation.overall_score if evaluation else None,
        weighted_utility_score=weighted_utility_score,
        evidence_count=evidence_count,
        evidence_score=evidence_score,
        estimated_complexity=estimated_complexity,
        complexity_score=complexity_score,
        confidence=confidence,
        recommendation=evaluation.recommendation if evaluation else None,
        drivers=_drivers(unit, evaluation, evidence_count, estimated_complexity),
        warnings=_warnings(evaluation, evidence_count),
    )


def _resolve_profile_weights(profile: Any) -> tuple[str | None, str, dict[str, float]]:
    if profile is None:
        return None, "default", dict(DEFAULT_WEIGHTS)

    if isinstance(profile, str):
        return profile, profile, dict(get_weights(profile))

    evaluation_config = getattr(profile, "evaluation", profile)
    profile_name = getattr(profile, "name", None)
    weight_profile = getattr(evaluation_config, "weight_profile", "default")
    custom_weights = getattr(evaluation_config, "custom_weights", None)
    if isinstance(profile, Mapping):
        profile_name = profile.get("name")
        evaluation_config = profile.get("evaluation", profile)
        if isinstance(evaluation_config, Mapping):
            weight_profile = str(evaluation_config.get("weight_profile", weight_profile))
            custom_weights = evaluation_config.get("custom_weights")

    weights = dict(custom_weights or get_weights(str(weight_profile)))
    total = sum(weights.values())
    if total > 0:
        weights = {dimension: round(float(weight) / total, 4) for dimension, weight in weights.items()}
    return profile_name, str(weight_profile), weights


def _weighted_utility_score(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    weights: dict[str, float],
) -> float:
    if evaluation is None:
        fallback_scores = [
            score
            for score in (unit.quality_score, unit.novelty_score, unit.usefulness_score)
            if score
        ]
        if not fallback_scores:
            return 0.0
        average = sum(fallback_scores) / len(fallback_scores)
        return round(max(0.0, min(100.0, average * 10.0)), 1)

    score = sum(getattr(evaluation, dimension).value * weights.get(dimension, 0.0) for dimension in DIMENSIONS)
    return round(max(0.0, min(100.0, score * 10.0)), 1)


def _estimated_complexity(unit: BuildableUnit, evaluation: UtilityEvaluation | None) -> float:
    if evaluation is not None:
        return round(max(1.0, min(10.0, 10.0 - evaluation.build_effort.value)), 1)

    base_by_category = {
        "feature": 3.0,
        "automation": 3.5,
        "cli_tool": 4.0,
        "library": 4.5,
        "integration": 5.0,
        "mcp_server": 5.0,
        "application": 6.0,
    }
    complexity = base_by_category.get(str(unit.category), 5.0)
    complexity += min(len(unit.domain_risks), 3) * 0.5
    complexity += min(len(unit.suggested_stack or {}), 6) * 0.15
    if unit.source_idea_ids:
        complexity += min(len(unit.source_idea_ids), 3) * 0.25
    if len(unit.tech_approach) > 240:
        complexity += 0.5
    return round(max(1.0, min(10.0, complexity)), 1)


def _evidence_count(unit: BuildableUnit) -> int:
    return len(set(unit.inspiring_insights) | set(unit.evidence_signals))


def _confidence(evaluation: UtilityEvaluation | None, evidence_count: int) -> float:
    evidence_confidence = min(evidence_count / 5.0, 1.0)
    if evaluation is None:
        return round(evidence_confidence * 0.6, 3)
    dimension_confidence = sum(
        getattr(evaluation, dimension).confidence for dimension in DIMENSIONS
    ) / len(DIMENSIONS)
    return round(min(1.0, dimension_confidence * 0.65 + evidence_confidence * 0.35), 3)


def _drivers(
    unit: BuildableUnit,
    evaluation: UtilityEvaluation | None,
    evidence_count: int,
    estimated_complexity: float,
) -> list[str]:
    drivers: list[str] = []
    if evaluation is not None:
        top_dimension = max(DIMENSIONS, key=lambda dimension: getattr(evaluation, dimension).value)
        drivers.append(f"strongest_dimension:{top_dimension}")
        if evaluation.recommendation in {"strong_yes", "yes"}:
            drivers.append(f"recommendation:{evaluation.recommendation}")
    if evidence_count >= 5:
        drivers.append("evidence:strong")
    elif evidence_count >= 2:
        drivers.append("evidence:moderate")
    if estimated_complexity <= 3.0:
        drivers.append("complexity:low")
    elif estimated_complexity >= 7.0:
        drivers.append("complexity:high")
    if unit.quality_score:
        drivers.append("quality_signal:present")
    return drivers


def _warnings(evaluation: UtilityEvaluation | None, evidence_count: int) -> list[str]:
    warnings: list[str] = []
    if evaluation is None:
        warnings.append("No utility evaluation available; utility score uses idea quality fields only.")
    if evidence_count == 0:
        warnings.append("No direct evidence references attached.")
    elif evidence_count < 2:
        warnings.append("Evidence is thin; validate before treating ROI as reliable.")
    return warnings
