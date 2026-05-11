"""Feature adoption cohort export for launch-period adoption analysis."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.feature_adoption_cohorts.v1"
KIND = "max.feature_adoption_cohorts"

_VALID_PERIODS = {"week", "month"}


def build_feature_adoption_cohorts_export(
    store: Store,
    domain: str | None = None,
    period: str = "month",
) -> dict[str, Any]:
    """Build feature launch cohorts from buildable unit adoption metadata."""
    if period not in _VALID_PERIODS:
        raise ValueError("period must be 'week' or 'month'")

    units = store.get_buildable_units(limit=1000, domain=domain)
    cohorts = _build_cohorts(units, period)
    summary = _build_summary(cohorts, len(units), period)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "feature_adoption_cohorts",
            "domain_filter": domain,
            "period": period,
            "defaults": {
                "feature_name": "Untitled feature",
                "segment": "unknown",
                "eligible_users": 0,
                "activated_users": 0,
                "retained_users": 0,
            },
        },
        "cohorts": cohorts,
        "summary": summary,
        "recommendations": _build_recommendations(cohorts, summary),
    }


def render_feature_adoption_cohorts_markdown(report: dict[str, Any]) -> str:
    """Render feature adoption cohorts as Markdown."""
    summary = report.get("summary", {})
    source = report.get("source", {})
    lines = [
        "# Feature Adoption Cohorts",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Period: {source.get('period', 'month')}",
        "",
        "## Summary",
        "",
        f"- Cohorts analyzed: {summary.get('cohort_count', 0)}",
        f"- Buildable units: {summary.get('unit_count', 0)}",
        f"- Eligible users: {summary.get('eligible_users', 0):,}",
        f"- Activated users: {summary.get('activated_users', 0):,}",
        f"- Retained users: {summary.get('retained_users', 0):,}",
        f"- Average adoption: {summary.get('average_adoption_pct', 0.0):.1f}%",
        f"- Average retention: {summary.get('average_retention_pct', 0.0):.1f}%",
        f"- Low adoption cohorts: {summary.get('low_adoption_cohort_count', 0)}",
        "",
        "## Cohort Table",
        "",
    ]

    if report.get("cohorts"):
        lines.extend([
            "| Period | Feature | Segment | Units | Eligible | Activated | Retained | Adoption | Retention |",
            "|--------|---------|---------|-------|----------|-----------|----------|----------|-----------|",
        ])
        for cohort in report["cohorts"]:
            lines.append(
                f"| {cohort['period']} | {cohort['feature_name']} | {cohort['segment']} | "
                f"{cohort['unit_count']} | {cohort['eligible_users']:,} | "
                f"{cohort['activated_users']:,} | {cohort['retained_users']:,} | "
                f"{cohort['adoption_pct']:.1f}% | {cohort['retention_pct']:.1f}% |"
            )
    else:
        lines.append(
            "- No feature adoption cohorts available. Add buildable units with feature launch "
            "and adoption metadata to start tracking cohort performance."
        )

    lines.extend(["", "## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_feature_adoption_cohorts_json(report: dict[str, Any]) -> str:
    """Render feature adoption cohorts as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _build_cohorts(units: list[Any], period: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        row = _unit_activity(unit, period)
        groups[(row["period"], row["feature_name"], row["segment"])].append(row)

    cohorts: list[dict[str, Any]] = []
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda row: (row["title"], row["idea_id"]))
        eligible_users = sum(row["eligible_users"] for row in rows)
        activated_users = sum(row["activated_users"] for row in rows)
        retained_users = sum(row["retained_users"] for row in rows)
        launch_dates = [row["launched_at"] for row in rows if row["launched_at"]]
        cohorts.append({
            "period": key[0],
            "period_start": _period_start(_parse_period_label(key[0], period), period).date().isoformat(),
            "feature_name": key[1],
            "segment": key[2],
            "unit_count": len(rows),
            "idea_ids": [row["idea_id"] for row in rows],
            "eligible_users": eligible_users,
            "activated_users": activated_users,
            "retained_users": retained_users,
            "adoption_pct": _percentage(activated_users, eligible_users),
            "retention_pct": _percentage(retained_users, activated_users),
            "launch_dates": launch_dates,
            "activity": rows,
        })
    return cohorts


def _unit_activity(unit: Any, period: str) -> dict[str, Any]:
    metadata = _metadata(unit)
    launched_at = _launch_date(unit, metadata)
    eligible_users = _non_negative_int(_number_from_metadata(metadata, ["eligible_users"], 0))
    activated_users = _non_negative_int(_number_from_metadata(metadata, ["activated_users"], 0))
    retained_users = _non_negative_int(_number_from_metadata(metadata, ["retained_users"], 0))
    feature_name = _string_from_metadata(metadata, ["feature_name", "feature"], "") or str(getattr(unit, "title", "Untitled feature"))
    segment = _string_from_metadata(metadata, ["segment", "account_segment", "customer_segment"], "unknown").lower()

    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": str(getattr(unit, "title", "Untitled")),
        "feature_name": feature_name or "Untitled feature",
        "segment": segment or "unknown",
        "launched_at": launched_at.date().isoformat(),
        "period": _period_label(launched_at, period),
        "eligible_users": eligible_users,
        "activated_users": activated_users,
        "retained_users": retained_users,
        "adoption_pct": _percentage(activated_users, eligible_users),
        "retention_pct": _percentage(retained_users, activated_users),
    }


def _build_summary(cohorts: list[dict[str, Any]], unit_count: int, period: str) -> dict[str, Any]:
    eligible_users = sum(cohort["eligible_users"] for cohort in cohorts)
    activated_users = sum(cohort["activated_users"] for cohort in cohorts)
    retained_users = sum(cohort["retained_users"] for cohort in cohorts)
    adoption_rates = [cohort["adoption_pct"] for cohort in cohorts]
    retention_rates = [cohort["retention_pct"] for cohort in cohorts]

    if not cohorts:
        narrative = (
            "No feature adoption cohorts are available yet. Add feature_name, launched_at, "
            f"eligible_users, activated_users, and retained_users metadata, then rerun the {period} report."
        )
    else:
        narrative = (
            f"Analyzed {len(cohorts)} {period} feature adoption cohort(s) across "
            f"{unit_count} buildable unit(s)."
        )

    return {
        "period": period,
        "cohort_count": len(cohorts),
        "unit_count": unit_count,
        "feature_count": len({cohort["feature_name"] for cohort in cohorts}),
        "segment_count": len({cohort["segment"] for cohort in cohorts}),
        "eligible_users": eligible_users,
        "activated_users": activated_users,
        "retained_users": retained_users,
        "overall_adoption_pct": _percentage(activated_users, eligible_users),
        "overall_retention_pct": _percentage(retained_users, activated_users),
        "average_adoption_pct": round(sum(adoption_rates) / len(adoption_rates), 1) if adoption_rates else 0.0,
        "average_retention_pct": round(sum(retention_rates) / len(retention_rates), 1) if retention_rates else 0.0,
        "low_adoption_cohort_count": sum(1 for cohort in cohorts if cohort["eligible_users"] > 0 and cohort["adoption_pct"] < 25.0),
        "zero_eligible_cohort_count": sum(1 for cohort in cohorts if cohort["eligible_users"] == 0),
        "narrative": narrative,
    }


def _build_recommendations(
    cohorts: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[str]:
    if not cohorts:
        return [
            "Add launch dates and adoption counts to buildable unit metadata before interpreting feature adoption.",
            "Start with weekly cohorts for new launches and monthly cohorts for mature features.",
        ]

    recommendations: list[str] = []
    if summary["zero_eligible_cohort_count"]:
        recommendations.append("Backfill eligible user counts for cohorts with missing denominator data.")
    if summary["low_adoption_cohort_count"]:
        recommendations.append("Review onboarding, release notes, and in-product prompts for cohorts below 25% adoption.")
    if summary["overall_retention_pct"] < 50.0 and summary["activated_users"] > 0:
        recommendations.append("Investigate retained-user drop-off for activated cohorts below 50% retention.")
    if not recommendations:
        recommendations.append("Continue monitoring adoption and retention by launch period and segment.")
    return recommendations


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _number_from_metadata(metadata: dict[str, Any], keys: list[str], default: float) -> float:
    for key in keys:
        if key in metadata:
            return _coerce_float(metadata[key], default)
    for nested_key in ("adoption", "feature_adoption", "usage", "analytics"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if key in nested:
                    return _coerce_float(nested[key], default)
    return default


def _string_from_metadata(metadata: dict[str, Any], keys: list[str], default: str) -> str:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            return str(value).strip()
    for nested_key in ("adoption", "feature_adoption", "usage", "analytics"):
        nested = metadata.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value is not None and value != "":
                    return str(value).strip()
    return default


def _launch_date(unit: Any, metadata: dict[str, Any]) -> datetime:
    for value in (
        metadata.get("launched_at"),
        metadata.get("launch_date"),
        _nested_value(metadata, ["adoption", "feature_adoption"], "launched_at"),
        getattr(unit, "created_at", None),
        getattr(unit, "updated_at", None),
    ):
        if value:
            return _coerce_datetime(value)
    return datetime.now(timezone.utc)


def _nested_value(metadata: dict[str, Any], containers: list[str], key: str) -> Any:
    for container in containers:
        nested = metadata.get(container)
        if isinstance(nested, dict) and nested.get(key):
            return nested[key]
    return None


def _coerce_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _non_negative_int(value: float) -> int:
    return max(0, int(value))


def _percentage(numerator: int, denominator: int) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


def _coerce_datetime(value: Any) -> datetime:
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str) and value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.now(timezone.utc)
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _period_start(dt: datetime, period: str) -> datetime:
    dt = dt.astimezone(timezone.utc)
    if period == "week":
        start = dt - timedelta(days=dt.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_label(dt: datetime, period: str) -> str:
    start = _period_start(dt, period)
    if period == "week":
        year, week, _ = start.isocalendar()
        return f"{year}-W{week:02d}"
    return start.strftime("%Y-%m")


def _parse_period_label(label: str, period: str) -> datetime:
    if period == "week":
        year, week = label.split("-W", 1)
        return datetime.fromisocalendar(int(year), int(week), 1).replace(tzinfo=timezone.utc)
    return datetime.strptime(label, "%Y-%m").replace(tzinfo=timezone.utc)
