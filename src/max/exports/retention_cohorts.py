"""Retention cohort export for recurring evidence activity analysis."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.retention_cohorts.v1"
KIND = "max.retention_cohorts"

_VALID_PERIODS = {"week", "month"}


def build_retention_cohort_export(
    store: Store,
    domain: str | None = None,
    period: str = "month",
) -> dict[str, Any]:
    """Build retention cohorts from buildable units and linked evidence signals."""
    if period not in _VALID_PERIODS:
        raise ValueError("period must be 'week' or 'month'")

    units = store.get_buildable_units(limit=1000, domain=domain)
    signals = store.get_signals(limit=1000)

    signal_by_id = {str(getattr(signal, "id", "")): signal for signal in signals}
    cohorts = _build_cohorts(units, signal_by_id, period)
    summary = _build_summary(cohorts, len(units), period)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "project": "max",
            "entity_type": "retention_cohorts",
            "domain_filter": domain,
            "period": period,
        },
        "cohorts": cohorts,
        "summary": summary,
        "recommendations": _build_recommendations(cohorts, summary),
    }


def render_retention_cohort_markdown(report: dict[str, Any]) -> str:
    """Render retention cohort report as Markdown."""
    source = report.get("source", {})
    period = source.get("period", "month")
    summary = report.get("summary", {})
    lines = [
        "# Retention Cohort Analysis",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        f"Period: {period}",
        "",
        "## Summary",
        "",
        f"- Cohorts analyzed: {summary.get('cohort_count', 0)}",
        f"- Buildable units: {summary.get('unit_count', 0)}",
        f"- Evidence signals: {summary.get('evidence_signal_count', 0)}",
        f"- Average latest retention: {summary.get('average_latest_retention_pct', 0.0):.1f}%",
        f"- Cohorts with expansion: {summary.get('cohorts_with_expansion', 0)}",
        f"- At-risk cohorts: {summary.get('at_risk_cohort_count', 0)}",
        "",
    ]

    lines.extend(["## Cohort Table", ""])
    if report.get("cohorts"):
        lines.extend([
            "| Cohort | Units | Evidence | Latest Retention | Expanded | Dropped | Risk Notes |",
            "|--------|-------|----------|------------------|----------|---------|------------|",
        ])
        for cohort in report["cohorts"]:
            latest = cohort.get("latest_period", {})
            risk_notes = "; ".join(cohort.get("risk_notes", [])) or "No material risk notes"
            lines.append(
                f"| {cohort['cohort']} | {cohort['unit_count']} | "
                f"{cohort['evidence_signal_count']} | "
                f"{latest.get('retention_pct', 0.0):.1f}% | "
                f"{latest.get('expanded_units', 0)} | "
                f"{latest.get('dropped_units', 0)} | {risk_notes} |"
            )
        lines.append("")
    else:
        lines.extend(["- No cohorts available. Add buildable units with dated evidence signals to start tracking recurring usage.", ""])

    lines.extend(["## Cohort Activity", ""])
    for cohort in report.get("cohorts", []):
        lines.extend([
            f"### {cohort['cohort']}",
            "",
            "| Period | Active Units | Evidence | Retention | Expanded | Dropped |",
            "|--------|--------------|----------|-----------|----------|---------|",
        ])
        for activity in cohort.get("activity", []):
            lines.append(
                f"| {activity['period']} | {activity['active_units']} | "
                f"{activity['evidence_count']} | {activity['retention_pct']:.1f}% | "
                f"{activity['expanded_units']} | {activity['dropped_units']} |"
            )
        lines.append("")

        expansion_signals = cohort.get("expansion_signals", [])
        lines.extend(["**Expansion Signals**", ""])
        if expansion_signals:
            for signal in expansion_signals:
                lines.append(f"- {signal['title']} ({signal['period']})")
        else:
            lines.append("- No expansion signals detected")
        lines.append("")

        lines.extend(["**Risk Notes**", ""])
        for note in cohort.get("risk_notes", []) or ["No material risk notes"]:
            lines.append(f"- {note}")
        lines.append("")

    lines.extend(["## Recommendations", ""])
    for recommendation in report.get("recommendations", []):
        lines.append(f"- {recommendation}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_retention_cohort_json(report: dict[str, Any]) -> str:
    """Render retention cohort report as stable formatted JSON."""
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _build_cohorts(
    units: list[Any],
    signal_by_id: dict[str, Any],
    period: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for unit in sorted(units, key=lambda item: (_period_label(_unit_date(item), period), str(getattr(item, "id", "")))):
        grouped[_period_label(_unit_date(unit), period)].append(unit)

    cohorts: list[dict[str, Any]] = []
    for cohort_label in sorted(grouped):
        cohort_units = grouped[cohort_label]
        unit_signal_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        signal_rows: list[dict[str, str]] = []

        for unit in cohort_units:
            unit_id = str(getattr(unit, "id", ""))
            for signal_id in _evidence_signal_ids(unit):
                signal = signal_by_id.get(signal_id)
                if signal is None:
                    continue
                signal_period = _period_label(_signal_date(signal), period)
                unit_signal_counts[unit_id][signal_period] += 1
                signal_rows.append({
                    "id": signal_id,
                    "title": str(getattr(signal, "title", "Untitled signal")),
                    "period": signal_period,
                })

        period_labels = _activity_periods(cohort_label, signal_rows, period)
        activity = _build_activity(cohort_units, unit_signal_counts, period_labels)
        evidence_count = len(signal_rows)
        expansion_signals = _expansion_signals(signal_rows, activity)
        latest_period = activity[-1] if activity else _empty_activity_period(cohort_label)
        risk_notes = _risk_notes(cohort_units, evidence_count, latest_period)

        cohorts.append({
            "cohort": cohort_label,
            "cohort_start": _period_start(_unit_date(cohort_units[0]), period).date().isoformat(),
            "unit_count": len(cohort_units),
            "unit_ids": sorted(str(getattr(unit, "id", "")) for unit in cohort_units),
            "evidence_signal_count": evidence_count,
            "activity": activity,
            "latest_period": latest_period,
            "retention_pct": latest_period["retention_pct"],
            "expansion_signals": expansion_signals,
            "risk_notes": risk_notes,
        })

    return cohorts


def _build_activity(
    units: list[Any],
    unit_signal_counts: dict[str, dict[str, int]],
    period_labels: list[str],
) -> list[dict[str, Any]]:
    unit_ids = [str(getattr(unit, "id", "")) for unit in units]
    previous_active: set[str] = set()
    previous_counts = {unit_id: 0 for unit_id in unit_ids}
    activity: list[dict[str, Any]] = []

    for index, label in enumerate(period_labels):
        current_counts = {
            unit_id: unit_signal_counts.get(unit_id, {}).get(label, 0)
            for unit_id in unit_ids
        }
        active = {unit_id for unit_id, count in current_counts.items() if count > 0}
        retained = active if index == 0 else active & previous_active
        expanded = {
            unit_id
            for unit_id, count in current_counts.items()
            if index > 0 and count > 0
        }
        dropped = set() if index == 0 else previous_active - active
        evidence_count = sum(current_counts.values())
        retention_pct = round((len(active) / len(unit_ids)) * 100, 1) if unit_ids else 0.0

        activity.append({
            "period": label,
            "active_units": len(active),
            "evidence_count": evidence_count,
            "retained_units": len(retained),
            "expanded_units": len(expanded),
            "dropped_units": len(dropped),
            "retention_pct": retention_pct,
        })

        previous_active = active
        previous_counts = current_counts

    return activity


def _build_summary(cohorts: list[dict[str, Any]], unit_count: int, period: str) -> dict[str, Any]:
    evidence_count = sum(cohort["evidence_signal_count"] for cohort in cohorts)
    latest_retention = [cohort["latest_period"]["retention_pct"] for cohort in cohorts]
    at_risk = [
        cohort for cohort in cohorts
        if cohort["unit_count"] > 0 and cohort["latest_period"]["retention_pct"] < 50.0
    ]
    if not cohorts:
        narrative = (
            "No retention cohorts are available yet. Add buildable units and validation "
            f"signals, then rerun the {period} cohort report."
        )
    else:
        narrative = (
            f"Analyzed {len(cohorts)} {period} cohort(s) across {unit_count} buildable "
            f"unit(s) and {evidence_count} linked evidence signal(s)."
        )

    return {
        "period": period,
        "cohort_count": len(cohorts),
        "unit_count": unit_count,
        "evidence_signal_count": evidence_count,
        "average_latest_retention_pct": round(sum(latest_retention) / len(latest_retention), 1) if latest_retention else 0.0,
        "cohorts_with_expansion": sum(1 for cohort in cohorts if cohort["expansion_signals"]),
        "at_risk_cohort_count": len(at_risk),
        "narrative": narrative,
    }


def _build_recommendations(
    cohorts: list[dict[str, Any]],
    summary: dict[str, Any],
) -> list[str]:
    if not cohorts:
        return [
            "Instrument validation activity so recurring evidence can be tied back to buildable units.",
            "Create at least one weekly or monthly review cadence before interpreting retention.",
        ]

    recommendations: list[str] = []
    if summary["at_risk_cohort_count"]:
        recommendations.append("Prioritize follow-up interviews or usage checks for cohorts below 50% latest retention.")
    if summary["cohorts_with_expansion"]:
        recommendations.append("Package repeated expansion signals into proof points for roadmap and GTM planning.")
    if summary["evidence_signal_count"] < summary["unit_count"]:
        recommendations.append("Backfill evidence links for buildable units with no validation activity.")
    if not recommendations:
        recommendations.append("Continue monitoring recurring evidence cadence and watch for cohort-level drops.")
    return recommendations


def _activity_periods(cohort_label: str, signals: list[dict[str, str]], period: str) -> list[str]:
    latest_label = max([cohort_label, *(signal["period"] for signal in signals)])
    labels = [cohort_label]
    current = _parse_period_label(cohort_label, period)
    latest = _parse_period_label(latest_label, period)
    while current < latest:
        current = _next_period(current, period)
        labels.append(_period_label(current, period))
    return labels


def _expansion_signals(
    signal_rows: list[dict[str, str]],
    activity: list[dict[str, Any]],
) -> list[dict[str, str]]:
    expansion_periods = {
        row["period"] for row in activity
        if row["expanded_units"] > 0 and row["evidence_count"] > 0
    }
    rows = [row for row in signal_rows if row["period"] in expansion_periods]
    return sorted(rows, key=lambda row: (row["period"], row["title"], row["id"]))[:5]


def _risk_notes(units: list[Any], evidence_count: int, latest_period: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if evidence_count == 0:
        notes.append("No linked validation evidence for this cohort")
    if latest_period["retention_pct"] < 50.0 and units:
        notes.append("Latest retention is below 50%")
    if latest_period["dropped_units"] > 0:
        notes.append(f"{latest_period['dropped_units']} unit(s) dropped activity in the latest period")
    units_without_evidence = [
        str(getattr(unit, "id", ""))
        for unit in units
        if not _evidence_signal_ids(unit)
    ]
    if units_without_evidence:
        notes.append(f"{len(units_without_evidence)} unit(s) have no evidence links")
    return notes


def _evidence_signal_ids(unit: Any) -> list[str]:
    ids = getattr(unit, "evidence_signals", []) or []
    if isinstance(ids, str):
        try:
            parsed = json.loads(ids)
        except json.JSONDecodeError:
            parsed = [ids]
        ids = parsed
    return [str(signal_id) for signal_id in ids if str(signal_id)]


def _unit_date(unit: Any) -> datetime:
    return _coerce_datetime(getattr(unit, "created_at", None) or getattr(unit, "updated_at", None))


def _signal_date(signal: Any) -> datetime:
    return _coerce_datetime(getattr(signal, "published_at", None) or getattr(signal, "fetched_at", None))


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
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


def _next_period(dt: datetime, period: str) -> datetime:
    if period == "week":
        return dt + timedelta(days=7)
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


def _empty_activity_period(label: str) -> dict[str, Any]:
    return {
        "period": label,
        "active_units": 0,
        "evidence_count": 0,
        "retained_units": 0,
        "expanded_units": 0,
        "dropped_units": 0,
        "retention_pct": 0.0,
    }
