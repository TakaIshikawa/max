"""Calibration report comparing evaluation scores to review feedback."""

from __future__ import annotations

from dataclasses import dataclass

from max.store.db import Store

APPROVED_OUTCOMES = {"approved", "published"}
REJECTED_OUTCOMES = {"rejected", "abandoned"}
CALIBRATION_OUTCOMES = APPROVED_OUTCOMES | REJECTED_OUTCOMES

DEFAULT_MIN_SAMPLES = 1
DEFAULT_LIMIT = 50
DEFAULT_HIGH_SCORE_THRESHOLD = 80.0
DEFAULT_LOW_SCORE_THRESHOLD = 50.0
DEFAULT_BUCKET_SIZE = 20


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
    terminal approval/rejection outcomes. This keeps calibration aligned with
    the current review decision without changing evaluation scoring behavior.
    """
    min_samples = max(1, int(min_samples))
    limit = max(1, int(limit))
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
    return [dict(row) for row in rows]


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
    )


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
