"""Portfolio stage distribution report for buildable ideas."""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any


SCHEMA_VERSION = "max.portfolio_stage_distribution.v1"
UNEVALUATED_RECOMMENDATION = "unevaluated"
DEFAULT_BOTTLENECK_THRESHOLD = 0.5
_CSV_COLUMNS = (
    "row_type",
    "dimension",
    "value",
    "status",
    "recommendation",
    "profile",
    "domain",
    "evidence_strength",
    "count",
    "percentage",
    "message",
)
_BUCKET_SECTIONS = (
    ("status", "Status", "by_status"),
    ("recommendation", "Recommendation", "by_recommendation"),
    ("profile", "Profile", "by_profile"),
    ("domain", "Domain", "by_domain"),
    ("evidence_strength", "Evidence Strength", "by_evidence_strength"),
)


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


def render_portfolio_stage_distribution_report(
    report: Mapping[str, Any],
    fmt: str = "json",
) -> str:
    """Render a portfolio stage distribution report as deterministic JSON, Markdown, or CSV."""

    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "markdown":
        return render_portfolio_stage_distribution_markdown(report)
    if fmt == "csv":
        return render_portfolio_stage_distribution_csv(report)
    raise ValueError(f"Unsupported portfolio stage distribution format: {fmt}")


def render_portfolio_stage_distribution_markdown(report: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown summary of portfolio stage distribution."""

    summary = report.get("summary", {})
    lines = [
        "# Portfolio Stage Distribution",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        f"Profile filter: {_inline_list(_filter_list(report, 'profile')) or 'all'}",
        f"Domain filter: {_inline_list(_filter_list(report, 'domain')) or 'all'}",
        "",
        "## Summary",
        "",
        f"- Total ideas: {summary.get('total_ideas', 0)}",
        f"- Evaluated ideas: {summary.get('evaluated_count', 0)}",
        f"- Unevaluated ideas: {summary.get('unevaluated_count', 0)}",
        f"- Bottlenecks: {summary.get('bottleneck_count', 0)}",
        "",
        "## Bottlenecks",
        "",
    ]

    bottlenecks = list(report.get("bottlenecks", []))
    if bottlenecks:
        for bottleneck in bottlenecks:
            lines.append(
                "- "
                f"{bottleneck.get('dimension', 'unknown')}="
                f"{bottleneck.get('value', 'unknown')}: "
                f"{bottleneck.get('count', 0)} ideas "
                f"({float(bottleneck.get('percentage', 0.0)):.1f}%)"
            )
            message = _clean(bottleneck.get("message"))
            if message:
                lines.append(f"  - {message}")
    else:
        lines.append("- None")

    lines.extend(["", "## Recommendations", ""])
    recommendations = list(report.get("recommendations", []))
    if recommendations:
        lines.extend(f"- {recommendation}" for recommendation in recommendations)
    else:
        lines.append("- None")

    lines.extend(["", "## Buckets", ""])
    for dimension, title, key in _BUCKET_SECTIONS:
        lines.extend([f"### {title}", "", "| Value | Count | Percentage |", "| --- | ---: | ---: |"])
        rows = list(report.get(key, []))
        if rows:
            for row in rows:
                lines.append(
                    f"| {_markdown_cell(row.get(dimension, 'unspecified'))} "
                    f"| {row.get('count', 0)} "
                    f"| {float(row.get('percentage', 0.0)):.1f}% |"
                )
        else:
            lines.append("| None | 0 | 0.0% |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_portfolio_stage_distribution_csv(report: Mapping[str, Any]) -> str:
    """Render bucket, group, bottleneck, and recommendation rows as deterministic CSV."""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def render_portfolio_stage_distribution_json(report: Mapping[str, Any]) -> str:
    """Render portfolio stage distribution report as deterministic JSON."""
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


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


def _csv_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension, _title, key in _BUCKET_SECTIONS:
        for bucket in report.get(key, []):
            rows.append(
                _csv_row(
                    row_type="bucket",
                    dimension=dimension,
                    value=bucket.get(dimension, ""),
                    count=bucket.get("count", 0),
                    percentage=bucket.get("percentage", 0.0),
                )
            )

    for group in report.get("groups", []):
        rows.append(
            _csv_row(
                row_type="group",
                dimension="group",
                value=_group_value(group),
                status=group.get("status", ""),
                recommendation=group.get("recommendation", ""),
                profile=group.get("profile", ""),
                domain=group.get("domain", ""),
                evidence_strength=group.get("evidence_strength", ""),
                count=group.get("count", 0),
                percentage=group.get("percentage", 0.0),
            )
        )

    for bottleneck in report.get("bottlenecks", []):
        rows.append(
            _csv_row(
                row_type="bottleneck",
                dimension=bottleneck.get("dimension", ""),
                value=bottleneck.get("value", ""),
                count=bottleneck.get("count", 0),
                percentage=bottleneck.get("percentage", 0.0),
                message=bottleneck.get("message", ""),
            )
        )

    for index, recommendation in enumerate(report.get("recommendations", []), start=1):
        rows.append(
            _csv_row(
                row_type="recommendation",
                dimension="recommendation",
                value=str(index),
                message=recommendation,
            )
        )
    return rows


def _csv_row(
    *,
    row_type: str,
    dimension: Any = "",
    value: Any = "",
    status: Any = "",
    recommendation: Any = "",
    profile: Any = "",
    domain: Any = "",
    evidence_strength: Any = "",
    count: Any = "",
    percentage: Any = "",
    message: Any = "",
) -> dict[str, Any]:
    return {
        "row_type": row_type,
        "dimension": dimension,
        "value": value,
        "status": status,
        "recommendation": recommendation,
        "profile": profile,
        "domain": domain,
        "evidence_strength": evidence_strength,
        "count": count,
        "percentage": percentage,
        "message": message,
    }


def _group_value(group: Mapping[str, Any]) -> str:
    return "|".join(
        _clean(group.get(key))
        for key in ("status", "recommendation", "profile", "domain", "evidence_strength")
    )


def _filter_list(report: Mapping[str, Any], key: str) -> list[Any]:
    filters = report.get("filters", {})
    if not isinstance(filters, Mapping):
        return []
    value = filters.get(key)
    if value is None:
        return []
    return _list(value)


def _inline_list(values: Iterable[Any]) -> str:
    return ", ".join(_clean(value) for value in values if _clean(value))


def _markdown_cell(value: Any) -> str:
    return _clean(value).replace("|", "\\|") or "unspecified"
