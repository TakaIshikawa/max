"""Implementation timeline variance report export."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.implementation_timeline_variance_report.v1"
KIND = "max.implementation_timeline_variance_report"

_CATEGORY_ORDER = {"late": 0, "at_risk": 1, "on_track": 2, "early": 3, "unknown": 4}


def build_implementation_timeline_variance_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_milestone_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_CATEGORY_ORDER[row["variance_category"]], -row["variance_days"], row["milestone"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "implementation_timeline_variance_report", "domain_filter": domain},
        "summary": _summary(rows),
        "milestones": rows,
    }


def render_implementation_timeline_variance_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Implementation Timeline Variance Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Milestones", ""]
    if report.get("milestones"):
        lines.extend(["| Milestone | Category | Variance Days | Drivers | Corrective Action |", "|-----------|----------|---------------|---------|-------------------|"])
        for row in report["milestones"]:
            lines.append(f"| {_md(row['milestone'])} | {row['variance_category']} | {row['variance_days']} | {_md(', '.join(row['likely_drivers']) or 'None')} | {_md(row['recommended_corrective_action'])} |")
    else:
        lines.append("- No implementation milestones available.")
    return "\n".join(lines).rstrip() + "\n"


def render_implementation_timeline_variance_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _milestone_row(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}
    planned = _date(metadata.get("planned_date") or metadata.get("planned_end_date") or metadata.get("target_date"))
    actual = _date(metadata.get("actual_date") or metadata.get("actual_end_date") or metadata.get("completed_date"))
    planned_duration = _number(metadata.get("planned_duration_days"))
    actual_duration = _number(metadata.get("actual_duration_days"))
    if planned and actual:
        variance = (actual - planned).days
    elif planned_duration or actual_duration:
        variance = int(actual_duration - planned_duration)
    else:
        variance = 0
    category = "unknown" if not (planned or planned_duration or actual_duration) else "late" if actual and variance > 7 else "at_risk" if actual is None and variance >= 0 else "early" if variance < 0 else "on_track"
    drivers = _list(metadata.get("variance_drivers") or metadata.get("drivers") or metadata.get("blockers") or metadata.get("incidents"))
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "milestone": _text(metadata.get("milestone") or getattr(unit, "title", "Untitled")),
        "planned_date": planned.isoformat() if planned else None,
        "actual_date": actual.isoformat() if actual else None,
        "variance_days": variance,
        "variance_category": category,
        "likely_drivers": drivers,
        "recommended_corrective_action": _action(category, drivers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"milestone_count": len(rows), "average_variance_days": round(sum(row["variance_days"] for row in rows) / len(rows), 1) if rows else 0.0, "category_counts": {category: sum(1 for row in rows if row["variance_category"] == category) for category in ("late", "at_risk", "on_track", "early", "unknown")}}


def _action(category: str, drivers: list[str]) -> str:
    if category in {"late", "at_risk"}:
        return f"Assign a recovery owner for {drivers[0].lower()}." if drivers else "Confirm owner, dependency path, and revised milestone date."
    return "Keep milestone evidence current."


def _date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
