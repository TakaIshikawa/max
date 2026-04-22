"""Recommend review thresholds from historical evaluation feedback."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from max.store.db import Store

DEFAULT_APPROVE_THRESHOLD = 68.0
DEFAULT_REJECT_THRESHOLD = 50.0
DEFAULT_MIN_SAMPLES = 5

APPROVED_OUTCOMES = {"approved", "published"}
REJECTED_OUTCOMES = {"rejected", "abandoned"}


@dataclass(frozen=True)
class ReviewThresholdRecommendation:
    domain: str
    approve_threshold: float
    reject_threshold: float
    sample_count: int
    approved_count: int
    rejected_count: int
    sufficient_samples: bool
    fallback_used: bool
    reason: str


def recommend_review_thresholds(
    store: Store,
    *,
    domain: str | None = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    default_approve_threshold: float = DEFAULT_APPROVE_THRESHOLD,
    default_reject_threshold: float = DEFAULT_REJECT_THRESHOLD,
) -> list[ReviewThresholdRecommendation]:
    """Compute per-domain approve/reject thresholds from latest feedback.

    Only the latest feedback row for each evaluated idea is used, so a changed
    review decision replaces earlier feedback in the recommendation set.
    """
    min_samples = max(1, int(min_samples))
    rows = _latest_feedback_scores(store, domain=domain)

    by_domain: dict[str, list[tuple[float, str]]] = {}
    for row in rows:
        by_domain.setdefault(row["domain"] or "", []).append(
            (float(row["overall_score"]), str(row["outcome"]))
        )

    if domain is not None and domain not in by_domain:
        by_domain[domain] = []

    recommendations = [
        _recommend_for_domain(
            name,
            samples,
            min_samples=min_samples,
            default_approve_threshold=default_approve_threshold,
            default_reject_threshold=default_reject_threshold,
        )
        for name, samples in sorted(by_domain.items())
    ]
    return recommendations


def _latest_feedback_scores(store: Store, *, domain: str | None = None) -> list[dict]:
    params: list[str] = []
    conditions = ["lf.outcome IN ('approved', 'published', 'rejected', 'abandoned')"]
    if domain is not None:
        conditions.append("bu.domain = ?")
        params.append(domain)
    where = "WHERE " + " AND ".join(conditions)

    rows = store.conn.execute(
        f"""SELECT bu.domain, e.overall_score, lf.outcome
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
             ORDER BY bu.domain, e.overall_score""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _recommend_for_domain(
    domain: str,
    samples: list[tuple[float, str]],
    *,
    min_samples: int,
    default_approve_threshold: float,
    default_reject_threshold: float,
) -> ReviewThresholdRecommendation:
    approved = sorted(score for score, outcome in samples if outcome in APPROVED_OUTCOMES)
    rejected = sorted(score for score, outcome in samples if outcome in REJECTED_OUTCOMES)
    sample_count = len(approved) + len(rejected)

    if sample_count < min_samples:
        return ReviewThresholdRecommendation(
            domain=domain,
            approve_threshold=round(default_approve_threshold, 1),
            reject_threshold=round(default_reject_threshold, 1),
            sample_count=sample_count,
            approved_count=len(approved),
            rejected_count=len(rejected),
            sufficient_samples=False,
            fallback_used=True,
            reason=f"insufficient samples: {sample_count} < {min_samples}",
        )

    approve_threshold = _percentile(approved, 25) if approved else default_approve_threshold
    reject_threshold = _percentile(rejected, 75) if rejected else default_reject_threshold
    fallback_used = not approved or not rejected

    if approved and rejected and reject_threshold >= approve_threshold:
        approved_median = median(approved)
        rejected_median = median(rejected)
        if approved_median <= rejected_median:
            return ReviewThresholdRecommendation(
                domain=domain,
                approve_threshold=round(default_approve_threshold, 1),
                reject_threshold=round(default_reject_threshold, 1),
                sample_count=sample_count,
                approved_count=len(approved),
                rejected_count=len(rejected),
                sufficient_samples=True,
                fallback_used=True,
                reason="feedback scores overlap; using fallback defaults",
            )
        midpoint = (approved_median + rejected_median) / 2
        reject_threshold = midpoint - 2.5
        approve_threshold = midpoint + 2.5

    reason = "computed from approved and rejected feedback"
    if approved and not rejected:
        reason = "no rejected samples; reject threshold uses fallback default"
    elif rejected and not approved:
        reason = "no approved samples; approve threshold uses fallback default"

    return ReviewThresholdRecommendation(
        domain=domain,
        approve_threshold=round(_clamp(approve_threshold), 1),
        reject_threshold=round(_clamp(reject_threshold), 1),
        sample_count=sample_count,
        approved_count=len(approved),
        rejected_count=len(rejected),
        sufficient_samples=True,
        fallback_used=fallback_used,
        reason=reason,
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * (percentile / 100)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
