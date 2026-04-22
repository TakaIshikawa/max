"""Deterministic opportunity heatmap analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


APPROVED_OUTCOMES = {"approved", "published"}
APPROVED_STATUSES = {"approved", "published"}


@dataclass
class _Bucket:
    domain: str
    idea_category: str
    idea_ids: set[str] = field(default_factory=set)
    signal_ids: set[str] = field(default_factory=set)
    insight_ids: set[str] = field(default_factory=set)
    evaluated_ids: set[str] = field(default_factory=set)
    approved_ids: set[str] = field(default_factory=set)
    scores: list[float] = field(default_factory=list)
    fetched_at_values: list[datetime] = field(default_factory=list)
    newest_fetched_at: str | None = None
    evidence_density: float = 0.0
    freshness_signal: float = 0.0


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _as_value(value: Any) -> str:
    return getattr(value, "value", value) or "unspecified"


def _bucket_key(unit: BuildableUnit) -> tuple[str, str]:
    return (_as_value(unit.domain), _as_value(unit.category))


def _resolved_signal_ids(unit: BuildableUnit, store: Store, bucket: _Bucket) -> set[str]:
    signal_ids = set(unit.evidence_signals)
    for insight_id in unit.inspiring_insights:
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        bucket.insight_ids.add(insight.id)
        signal_ids.update(insight.evidence)
    return signal_ids


def _add_signal_evidence(signal_id: str, store: Store, bucket: _Bucket) -> None:
    signal = store.get_signal(signal_id)
    if not signal:
        return
    bucket.signal_ids.add(signal.id)
    fetched_at = _parse_dt(signal.fetched_at)
    if fetched_at is not None:
        bucket.fetched_at_values.append(fetched_at)


def _evidence_density(*, signal_count: int, insight_count: int, idea_count: int, evaluated_count: int) -> float:
    if idea_count <= 0:
        return 0.0

    signal_density = min(signal_count / max(idea_count * 3, 1), 1.0)
    insight_density = min(insight_count / max(idea_count * 2, 1), 1.0)
    evaluation_density = min(evaluated_count / idea_count, 1.0)
    return round(
        (signal_density * 0.60 + insight_density * 0.25 + evaluation_density * 0.15)
        * 100,
        1,
    )


def _assign_freshness_scores(buckets: list[_Bucket]) -> None:
    dated = [bucket for bucket in buckets if bucket.fetched_at_values]
    if not dated:
        return

    newest_values = sorted({max(bucket.fetched_at_values) for bucket in dated})
    max_index = len(newest_values) - 1

    for bucket in dated:
        newest = max(bucket.fetched_at_values)
        bucket.newest_fetched_at = newest.isoformat()
        if max_index == 0:
            bucket.freshness_signal = 100.0
        else:
            bucket.freshness_signal = round((newest_values.index(newest) / max_index) * 100, 1)


def _opportunity_score(bucket: _Bucket) -> tuple[float, list[str]]:
    idea_count = len(bucket.idea_ids)
    evaluated_count = len(bucket.evaluated_ids)
    approved_count = len(bucket.approved_ids)
    average_score = sum(bucket.scores) / len(bucket.scores) if bucket.scores else None
    approval_rate = approved_count / idea_count if idea_count else 0.0
    score_quality = (average_score or 0.0)

    score = (
        score_quality * 0.35
        + bucket.evidence_density * 0.25
        + bucket.freshness_signal * 0.20
        + approval_rate * 100 * 0.20
    )

    reasons: list[str] = []
    if average_score is not None:
        reasons.append(f"average evaluated score {average_score:.1f}")
    else:
        reasons.append("no evaluated ideas yet")
    reasons.append(
        f"{len(bucket.signal_ids)} signal(s) and {len(bucket.insight_ids)} insight(s) support "
        f"{idea_count} idea(s)"
    )
    if bucket.newest_fetched_at:
        reasons.append(f"newest evidence fetched at {bucket.newest_fetched_at}")
    else:
        reasons.append("no resolved fetched_at evidence")
    if approved_count:
        reasons.append(f"{approved_count} approved or published idea(s)")
    elif evaluated_count:
        reasons.append("evaluated ideas have no approval feedback yet")

    return round(score, 1), reasons


def _bucket_to_dict(bucket: _Bucket) -> dict[str, Any]:
    average_score = round(sum(bucket.scores) / len(bucket.scores), 1) if bucket.scores else None
    opportunity_score, reasons = _opportunity_score(bucket)
    return {
        "domain": bucket.domain,
        "idea_category": bucket.idea_category,
        "signal_count": len(bucket.signal_ids),
        "insight_count": len(bucket.insight_ids),
        "idea_count": len(bucket.idea_ids),
        "evaluated_count": len(bucket.evaluated_ids),
        "approved_count": len(bucket.approved_ids),
        "average_score": average_score,
        "evidence_density": bucket.evidence_density,
        "newest_fetched_at": bucket.newest_fetched_at,
        "freshness_signal": bucket.freshness_signal,
        "opportunity_score": opportunity_score,
        "reasons": reasons,
    }


def build_opportunity_heatmap(
    store: Store,
    domain: str | None = None,
    min_signals: int = 1,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Group stored opportunities by domain and idea category without LLM calls."""
    if min_signals < 0:
        raise ValueError("min_signals must be non-negative")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    units = store.get_buildable_units(limit=limit, domain=domain)
    buckets: dict[tuple[str, str], _Bucket] = {}

    for unit in units:
        key = _bucket_key(unit)
        bucket = buckets.setdefault(key, _Bucket(domain=key[0], idea_category=key[1]))
        bucket.idea_ids.add(unit.id)

        evaluation = store.get_evaluation(unit.id)
        if evaluation is not None:
            bucket.evaluated_ids.add(unit.id)
            bucket.scores.append(float(evaluation.overall_score))

        latest_feedback = store.get_latest_feedback(unit.id)
        feedback_outcome = latest_feedback["outcome"] if latest_feedback else None
        if unit.status in APPROVED_STATUSES or feedback_outcome in APPROVED_OUTCOMES:
            bucket.approved_ids.add(unit.id)

        for signal_id in _resolved_signal_ids(unit, store, bucket):
            _add_signal_evidence(signal_id, store, bucket)

    bucket_list = list(buckets.values())
    _assign_freshness_scores(bucket_list)

    for bucket in bucket_list:
        bucket.evidence_density = _evidence_density(
            signal_count=len(bucket.signal_ids),
            insight_count=len(bucket.insight_ids),
            idea_count=len(bucket.idea_ids),
            evaluated_count=len(bucket.evaluated_ids),
        )

    results = [
        _bucket_to_dict(bucket)
        for bucket in bucket_list
        if len(bucket.signal_ids) >= min_signals
    ]
    return sorted(
        results,
        key=lambda item: (
            -float(item["opportunity_score"]),
            str(item["domain"]),
            str(item["idea_category"]),
        ),
    )
