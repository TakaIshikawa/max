"""Portfolio stage distribution report for buildable ideas."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any


SCHEMA_VERSION = "max.portfolio_stage_distribution.v1"
UNEVALUATED_RECOMMENDATION = "unevaluated"
DEFAULT_BOTTLENECK_THRESHOLD = 0.5


def build_portfolio_stage_distribution_report(
    buildable_units: Iterable[Any],
    evaluations: Iterable[Any] | Mapping[str, Any],
    *,
    profile: str | Iterable[str] | None = None,
    domain: str | Iterable[str] | None = None,
    bottleneck_threshold: float = DEFAULT_BOTTLENECK_THRESHOLD,
) -> dict[str, Any]:
    """Build a JSON-ready stage distribution report for an idea portfolio."""

    evaluation_by_unit_id = _evaluations_by_unit_id(evaluations)
    profile_filter = _filter_values(profile)
    domain_filter = _filter_values(domain)

    filtered_units = [
        unit
        for unit in buildable_units
        if _matches_filter(_profile(unit), profile_filter)
        and _matches_filter(_domain(unit), domain_filter)
    ]

    rows = [_idea_row(unit, evaluation_by_unit_id.get(_unit_id(unit))) for unit in filtered_units]
    total = len(rows)

    status_counts = Counter(row["status"] for row in rows)
    recommendation_counts = Counter(row["recommendation"] for row in rows)
    profile_counts = Counter(row["profile"] for row in rows)
    domain_counts = Counter(row["domain"] for row in rows)
    evidence_counts = Counter(row["evidence_strength"] for row in rows)
    grouped_counts = Counter(
        (
            row["status"],
            row["recommendation"],
            row["profile"],
            row["domain"],
            row["evidence_strength"],
        )
        for row in rows
    )

    bottlenecks = _bottlenecks(
        status_counts=status_counts,
        recommendation_counts=recommendation_counts,
        evidence_counts=evidence_counts,
        total=total,
        threshold=bottleneck_threshold,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.portfolio_stage_distribution",
        "filters": {
            "profile": sorted(profile_filter) if profile_filter else None,
            "domain": sorted(domain_filter) if domain_filter else None,
        },
        "summary": {
            "total_ideas": total,
            "evaluated_count": sum(
                1 for row in rows if row["recommendation"] != UNEVALUATED_RECOMMENDATION
            ),
            "unevaluated_count": recommendation_counts.get(UNEVALUATED_RECOMMENDATION, 0),
            "bottleneck_count": len(bottlenecks),
        },
        "by_status": _bucket_rows(status_counts, total, "status"),
        "by_recommendation": _bucket_rows(recommendation_counts, total, "recommendation"),
        "by_profile": _bucket_rows(profile_counts, total, "profile"),
        "by_domain": _bucket_rows(domain_counts, total, "domain"),
        "by_evidence_strength": _bucket_rows(evidence_counts, total, "evidence_strength"),
        "groups": _group_rows(grouped_counts, total),
        "bottlenecks": bottlenecks,
        "recommendations": _recommendations(bottlenecks, total),
    }


def build_portfolio_stage_distribution(
    buildable_units: Iterable[Any],
    evaluations: Iterable[Any] | Mapping[str, Any],
    *,
    profile: str | Iterable[str] | None = None,
    domain: str | Iterable[str] | None = None,
    bottleneck_threshold: float = DEFAULT_BOTTLENECK_THRESHOLD,
) -> dict[str, Any]:
    """Alias for callers that prefer the report name without the suffix."""

    return build_portfolio_stage_distribution_report(
        buildable_units,
        evaluations,
        profile=profile,
        domain=domain,
        bottleneck_threshold=bottleneck_threshold,
    )


def _idea_row(unit: Any, evaluation: Any | None) -> dict[str, Any]:
    evidence_score = _evidence_score(unit)
    return {
        "id": _unit_id(unit),
        "status": _clean(_get(unit, "status")) or "unspecified",
        "recommendation": _recommendation(evaluation),
        "profile": _profile(unit),
        "domain": _domain(unit),
        "evidence_strength": _evidence_strength(evidence_score),
        "evidence_score": evidence_score,
    }


def _evaluations_by_unit_id(evaluations: Iterable[Any] | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(evaluations, Mapping):
        return {str(unit_id): evaluation for unit_id, evaluation in evaluations.items()}

    indexed: dict[str, Any] = {}
    for evaluation in evaluations:
        unit_id = _clean(
            _get(evaluation, "buildable_unit_id")
            or _get(evaluation, "unit_id")
            or _get(evaluation, "idea_id")
            or _get(evaluation, "id")
        )
        if unit_id:
            indexed[unit_id] = evaluation
    return indexed


def _bottlenecks(
    *,
    status_counts: Counter[str],
    recommendation_counts: Counter[str],
    evidence_counts: Counter[str],
    total: int,
    threshold: float,
) -> list[dict[str, Any]]:
    if total == 0:
        return []

    bottlenecks: list[dict[str, Any]] = []
    for dimension, counts in (
        ("status", status_counts),
        ("recommendation", recommendation_counts),
        ("evidence_strength", evidence_counts),
    ):
        for value, count in sorted(counts.items()):
            percentage = _percentage(count, total)
            if count / total > threshold:
                bottlenecks.append(
                    {
                        "dimension": dimension,
                        "value": value,
                        "count": count,
                        "percentage": percentage,
                        "message": _bottleneck_message(dimension, value, percentage),
                    }
                )
    return sorted(
        bottlenecks,
        key=lambda item: (-item["count"], item["dimension"], item["value"]),
    )


def _recommendations(bottlenecks: list[dict[str, Any]], total: int) -> list[str]:
    if total == 0:
        return ["No matching ideas were found for the selected filters."]
    if not bottlenecks:
        return ["Portfolio stages are distributed below the bottleneck threshold."]
    return [item["message"] for item in bottlenecks]


def _bottleneck_message(dimension: str, value: str, percentage: float) -> str:
    if dimension == "status":
        return f"{percentage:.1f}% of ideas are in status '{value}'; promote, validate, or prune this stage next."
    if dimension == "recommendation":
        if value == UNEVALUATED_RECOMMENDATION:
            return f"{percentage:.1f}% of ideas are unevaluated; prioritize scoring before promotion decisions."
        return f"{percentage:.1f}% of ideas have recommendation '{value}'; review the next action for this cohort."
    return f"{percentage:.1f}% of ideas have '{value}' evidence; strengthen or prune weakly supported ideas."


def _bucket_rows(counts: Counter[str], total: int, key: str) -> list[dict[str, Any]]:
    return [
        {key: value, "count": count, "percentage": _percentage(count, total)}
        for value, count in sorted(counts.items())
    ]


def _group_rows(
    counts: Counter[tuple[str, str, str, str, str]],
    total: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (status, recommendation, profile, domain, evidence_strength), count in sorted(
        counts.items()
    ):
        rows.append(
            {
                "status": status,
                "recommendation": recommendation,
                "profile": profile,
                "domain": domain,
                "evidence_strength": evidence_strength,
                "count": count,
                "percentage": _percentage(count, total),
            }
        )
    return rows


def _recommendation(evaluation: Any | None) -> str:
    if evaluation is None:
        return UNEVALUATED_RECOMMENDATION
    return _clean(_get(evaluation, "recommendation")) or UNEVALUATED_RECOMMENDATION


def _evidence_strength(score: int) -> str:
    if score <= 0:
        return "none"
    if score == 1:
        return "weak"
    if score <= 3:
        return "moderate"
    return "strong"


def _evidence_score(unit: Any) -> int:
    evidence_counts = _get(unit, "evidence_counts")
    if isinstance(evidence_counts, Mapping):
        return sum(_int(value) for value in evidence_counts.values())

    fields = (
        "evidence_signals",
        "signal_ids",
        "inspiring_insights",
        "insight_ids",
        "source_idea_ids",
    )
    score = sum(len(_list(_get(unit, field))) for field in fields)
    if _clean(_get(unit, "evidence_rationale")):
        score += 1
    return score


def _profile(unit: Any) -> str:
    return _clean(
        _get(unit, "profile")
        or _get(unit, "profile_name")
        or _get(unit, "profile_id")
        or _get(unit, "source_profile")
        or _get(unit, "domain")
    ) or "unspecified"


def _domain(unit: Any) -> str:
    return _clean(_get(unit, "domain")) or "unspecified"


def _unit_id(unit: Any) -> str:
    return _clean(_get(unit, "id") or _get(unit, "buildable_unit_id") or _get(unit, "idea_id"))


def _matches_filter(value: str, allowed: set[str] | None) -> bool:
    return allowed is None or value in allowed


def _filter_values(value: str | Iterable[str] | None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = _clean(value)
        return {cleaned} if cleaned else None
    values = {_clean(item) for item in value}
    values.discard("")
    return values or None


def _get(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _percentage(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round((count / total) * 100, 1)
