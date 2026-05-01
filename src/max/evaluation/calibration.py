"""Calibration diagnostics comparing evaluation scores to review feedback."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from max.evaluation.explain import DIMENSION_LABELS
from max.evaluation.weights import DEFAULT_WEIGHTS
from max.store.db import Store

APPROVED_OUTCOMES = {"approved", "published"}
REJECTED_OUTCOMES = {"rejected", "abandoned"}
CALIBRATION_OUTCOMES = APPROVED_OUTCOMES | REJECTED_OUTCOMES

DEFAULT_MIN_SAMPLES = 1
DEFAULT_LIMIT = 50
DEFAULT_HIGH_SCORE_THRESHOLD = 80.0
DEFAULT_LOW_SCORE_THRESHOLD = 50.0
DEFAULT_BUCKET_SIZE = 20
MAX_WEIGHT_ADJUSTMENT = 0.03


@dataclass(frozen=True)
class CalibrationScoreBucket:
    min_score: float
    max_score: float
    sample_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    rejection_rate: float


@dataclass(frozen=True)
class CalibrationDimensionDiagnostic:
    dimension: str
    label: str
    sample_count: int
    approved_count: int
    rejected_count: int
    approved_average: float
    rejected_average: float
    score_delta: float
    direction: str
    confidence: str
    suggested_weight_delta: float
    current_weight: float
    suggested_weight: float


@dataclass(frozen=True)
class EvaluationCalibrationGroup:
    domain: str
    recommendation: str
    sample_count: int
    approved_count: int
    rejected_count: int
    approval_rate: float
    rejection_rate: float
    average_overall_score: float
    score_buckets: list[CalibrationScoreBucket]
    high_score_sample_count: int
    high_score_rejection_count: int
    high_score_rejection_rate: float
    low_score_sample_count: int
    low_score_approval_count: int
    low_score_approval_rate: float
    confidence: str = "low"
    dimension_diagnostics: list[CalibrationDimensionDiagnostic] = field(default_factory=list)
    suggested_weight_adjustments: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationCalibrationReport:
    domain: str | None
    min_samples: int
    limit: int
    high_score_threshold: float
    low_score_threshold: float
    total_groups: int
    total_samples: int
    groups: list[EvaluationCalibrationGroup]


def build_evaluation_calibration_report(
    store: Store,
    *,
    domain: str | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    limit: int = DEFAULT_LIMIT,
    high_score_threshold: float = DEFAULT_HIGH_SCORE_THRESHOLD,
    low_score_threshold: float = DEFAULT_LOW_SCORE_THRESHOLD,
    bucket_size: int = DEFAULT_BUCKET_SIZE,
) -> EvaluationCalibrationReport:
    """Build grouped score-vs-feedback calibration from evaluated ideas.

    The report uses only the latest feedback row for each idea and only
    terminal approval/rejection outcomes. It recommends bounded, deterministic
    weight adjustments for inspection, but does not mutate stored weight
    profiles.
    """
    min_samples = max(1, int(min_samples))
    limit = max(1, int(limit))
    bucket_size = max(1, int(bucket_size))
    rows = _latest_reviewed_evaluations(store, domain=domain)

    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        key = (row["domain"] or "", row["recommendation"] or "")
        grouped.setdefault(key, []).append(row)

    groups = [
        _summarize_group(
            group_domain,
            recommendation,
            samples,
            high_score_threshold=high_score_threshold,
            low_score_threshold=low_score_threshold,
            bucket_size=bucket_size,
        )
        for (group_domain, recommendation), samples in grouped.items()
        if len(samples) >= min_samples
    ]
    groups.sort(key=lambda item: (-item.sample_count, item.domain, item.recommendation))
    limited_groups = groups[:limit]

    return EvaluationCalibrationReport(
        domain=domain,
        min_samples=min_samples,
        limit=limit,
        high_score_threshold=high_score_threshold,
        low_score_threshold=low_score_threshold,
        total_groups=len(groups),
        total_samples=sum(group.sample_count for group in groups),
        groups=limited_groups,
    )


def _latest_reviewed_evaluations(store: Store, *, domain: str | None = None) -> list[dict]:
    params: list[str] = []
    conditions = ["lf.outcome IN ('approved', 'published', 'rejected', 'abandoned')"]
    if domain is not None:
        conditions.append("bu.domain = ?")
        params.append(domain)
    where = "WHERE " + " AND ".join(conditions)

    rows = store.conn.execute(
        f"""SELECT bu.domain,
                  e.recommendation,
                  e.overall_score,
                  e.pain_severity,
                  e.addressable_scale,
                  e.build_effort,
                  e.composability,
                  e.competitive_density,
                  e.timing_fit,
                  e.compounding_value,
                  lf.outcome
             FROM buildable_units bu
             JOIN evaluations e ON e.buildable_unit_id = bu.id
             JOIN (
                   SELECT f.*
                     FROM feedback f
                     JOIN (
                           SELECT buildable_unit_id, MAX(id) AS id
                             FROM feedback
                            GROUP BY buildable_unit_id
                          ) latest
                       ON latest.id = f.id
                  ) lf ON lf.buildable_unit_id = bu.id
            {where}
            ORDER BY bu.domain, e.recommendation, e.overall_score""",
        params,
    ).fetchall()
    return [_row_with_dimension_values(dict(row)) for row in rows]


def _row_with_dimension_values(row: dict) -> dict:
    dimension_values: dict[str, float] = {}
    for dimension in DEFAULT_WEIGHTS:
        raw = row.pop(dimension)
        value = json.loads(raw)["value"] if isinstance(raw, str) else 0.0
        dimension_values[dimension] = float(value)
    row["dimension_values"] = dimension_values
    return row


def _summarize_group(
    domain: str,
    recommendation: str,
    samples: list[dict],
    *,
    high_score_threshold: float,
    low_score_threshold: float,
    bucket_size: int,
) -> EvaluationCalibrationGroup:
    sample_count = len(samples)
    approved_count = sum(1 for row in samples if row["outcome"] in APPROVED_OUTCOMES)
    rejected_count = sum(1 for row in samples if row["outcome"] in REJECTED_OUTCOMES)
    score_total = sum(float(row["overall_score"]) for row in samples)

    high_score_samples = [
        row for row in samples if float(row["overall_score"]) >= high_score_threshold
    ]
    high_score_rejections = [
        row for row in high_score_samples if row["outcome"] in REJECTED_OUTCOMES
    ]
    low_score_samples = [
        row for row in samples if float(row["overall_score"]) < low_score_threshold
    ]
    low_score_approvals = [
        row for row in low_score_samples if row["outcome"] in APPROVED_OUTCOMES
    ]
    confidence = _confidence(sample_count, approved_count, rejected_count)
    diagnostics = _dimension_diagnostics(samples, confidence=confidence)

    return EvaluationCalibrationGroup(
        domain=domain,
        recommendation=recommendation,
        sample_count=sample_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        approval_rate=_rate(approved_count, sample_count),
        rejection_rate=_rate(rejected_count, sample_count),
        average_overall_score=round(score_total / sample_count, 2) if sample_count else 0.0,
        score_buckets=_score_buckets(samples, bucket_size=bucket_size),
        high_score_sample_count=len(high_score_samples),
        high_score_rejection_count=len(high_score_rejections),
        high_score_rejection_rate=_rate(len(high_score_rejections), len(high_score_samples)),
        low_score_sample_count=len(low_score_samples),
        low_score_approval_count=len(low_score_approvals),
        low_score_approval_rate=_rate(len(low_score_approvals), len(low_score_samples)),
        confidence=confidence,
        dimension_diagnostics=diagnostics,
        suggested_weight_adjustments={
            item.dimension: item.suggested_weight_delta for item in diagnostics
        },
    )


def _dimension_diagnostics(
    samples: list[dict],
    *,
    confidence: str,
) -> list[CalibrationDimensionDiagnostic]:
    diagnostics = [
        _dimension_diagnostic(dimension, samples, confidence=confidence)
        for dimension in DEFAULT_WEIGHTS
    ]
    diagnostics.sort(
        key=lambda item: (
            abs(item.suggested_weight_delta),
            abs(item.score_delta),
            item.dimension,
        ),
        reverse=True,
    )
    return diagnostics


def _dimension_diagnostic(
    dimension: str,
    samples: list[dict],
    *,
    confidence: str,
) -> CalibrationDimensionDiagnostic:
    approved = [row for row in samples if row["outcome"] in APPROVED_OUTCOMES]
    rejected = [row for row in samples if row["outcome"] in REJECTED_OUTCOMES]
    approved_average = _average_dimension(approved, dimension)
    rejected_average = _average_dimension(rejected, dimension)
    score_delta = round(approved_average - rejected_average, 2)
    direction = _dimension_direction(score_delta, len(approved), len(rejected))
    suggested_delta = _bounded_weight_delta(score_delta, confidence, len(approved), len(rejected))
    current_weight = DEFAULT_WEIGHTS[dimension]

    return CalibrationDimensionDiagnostic(
        dimension=dimension,
        label=DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title()),
        sample_count=len(samples),
        approved_count=len(approved),
        rejected_count=len(rejected),
        approved_average=approved_average,
        rejected_average=rejected_average,
        score_delta=score_delta,
        direction=direction,
        confidence=confidence,
        suggested_weight_delta=suggested_delta,
        current_weight=current_weight,
        suggested_weight=round(max(0.01, current_weight + suggested_delta), 4),
    )


def _dimension_direction(score_delta: float, approved_count: int, rejected_count: int) -> str:
    if not approved_count or not rejected_count:
        return "insufficient_outcome_diversity"
    if score_delta >= 1.0:
        return "underweighted_success_signal"
    if score_delta <= -1.0:
        return "overpredicting"
    return "mixed"


def _bounded_weight_delta(
    score_delta: float,
    confidence: str,
    approved_count: int,
    rejected_count: int,
) -> float:
    if not approved_count or not rejected_count:
        return 0.0
    multiplier = {"low": 0.25, "medium": 0.6, "high": 1.0}[confidence]
    scaled = (score_delta / 10.0) * MAX_WEIGHT_ADJUSTMENT * multiplier
    return round(max(-MAX_WEIGHT_ADJUSTMENT, min(MAX_WEIGHT_ADJUSTMENT, scaled)), 4)


def _confidence(sample_count: int, approved_count: int, rejected_count: int) -> str:
    if approved_count == 0 or rejected_count == 0 or sample_count < 8:
        return "low"
    if sample_count < 20:
        return "medium"
    return "high"


def _average_dimension(samples: list[dict], dimension: str) -> float:
    if not samples:
        return 0.0
    total = sum(row["dimension_values"].get(dimension, 0.0) for row in samples)
    return round(total / len(samples), 2)


def _score_buckets(samples: list[dict], *, bucket_size: int) -> list[CalibrationScoreBucket]:
    buckets: dict[float, dict[str, int | float]] = {}
    for row in samples:
        score = float(row["overall_score"])
        if score >= 100.0:
            min_score = float(max(0, 100 - bucket_size))
        else:
            min_score = float(int(score // bucket_size) * bucket_size)
        max_score = float(min(100, min_score + bucket_size))
        bucket = buckets.setdefault(
            min_score,
            {
                "min_score": min_score,
                "max_score": max_score,
                "sample_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
            },
        )
        bucket["sample_count"] = int(bucket["sample_count"]) + 1
        if row["outcome"] in APPROVED_OUTCOMES:
            bucket["approved_count"] = int(bucket["approved_count"]) + 1
        else:
            bucket["rejected_count"] = int(bucket["rejected_count"]) + 1

    return [
        CalibrationScoreBucket(
            min_score=float(bucket["min_score"]),
            max_score=float(bucket["max_score"]),
            sample_count=int(bucket["sample_count"]),
            approved_count=int(bucket["approved_count"]),
            rejected_count=int(bucket["rejected_count"]),
            approval_rate=_rate(int(bucket["approved_count"]), int(bucket["sample_count"])),
            rejection_rate=_rate(int(bucket["rejected_count"]), int(bucket["sample_count"])),
        )
        for bucket in sorted(buckets.values(), key=lambda item: float(item["min_score"]))
    ]


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
