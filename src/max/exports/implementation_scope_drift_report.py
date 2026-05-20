"""Implementation scope drift report export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.implementation_scope_drift_report.v1"
KIND = "max.implementation_scope_drift_report"

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_implementation_scope_drift_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_drift_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["drift_severity"]], -row["timeline_impact_days"], row["title"], row["idea_id"]))
    summary = _summary(rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "implementation_scope_drift_report", "domain_filter": domain},
        "summary": summary,
        "drift_rows": rows,
        "approval_gaps": [row for row in rows if row["approval_gap"]],
        "mitigation_actions": _mitigation_actions(rows, summary),
    }


def render_implementation_scope_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_implementation_scope_drift_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        "# Implementation Scope Drift Report",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Generated: {report['generated_at']}",
        "",
        "## Summary",
        "",
        f"- Units analyzed: {summary.get('unit_count', 0)}",
        f"- High drift: {summary.get('severity_counts', {}).get('high', 0)}",
        f"- Medium drift: {summary.get('severity_counts', {}).get('medium', 0)}",
        f"- Low drift: {summary.get('severity_counts', {}).get('low', 0)}",
        "",
        "## Drift Rows",
        "",
    ]
    if report.get("drift_rows"):
        lines.extend(["| Account | Title | Severity | Timeline | Approval | Drivers | Mitigation |", "|---------|-------|----------|----------|----------|---------|------------|"])
        for row in report["drift_rows"]:
            lines.append(
                f"| {_md(row['account'])} | {_md(row['title'])} | {row['drift_severity']} | {row['timeline_impact_days']} | "
                f"{_md(row['approval_status'])} | {_md(', '.join(row['drift_drivers']) or 'None')} | {_md(row['recommended_mitigation'])} |"
            )
    else:
        lines.append("- No implementation scope records found.")
    lines.extend(["", "## Mitigation Actions", ""])
    for action in report.get("mitigation_actions", []):
        lines.append(f"- {action}")
    return "\n".join(lines).rstrip() + "\n"


def _drift_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    added = _list(metadata.get("added_requirements"))
    removed = _list(metadata.get("removed_requirements"))
    changes = _list(metadata.get("change_requests"))
    timeline = max(0, int(_number(metadata.get("timeline_impact_days")) or 0))
    budget = _number(metadata.get("budget_impact")) or 0.0
    approval = _text(metadata.get("approval_status")).lower() or "unknown"
    approval_gap = approval not in {"approved", "accepted", "signed_off", "signed off"}
    score = len(added) * 20 + len(removed) * 12 + len(changes) * 18 + min(timeline * 2, 40) + min(abs(budget) / 1000, 30)
    if approval_gap and (added or changes or timeline or budget):
        score += 25
    severity = "high" if score >= 70 else "medium" if score >= 30 else "low"
    drivers = []
    if added:
        drivers.append("added_requirements")
    if removed:
        drivers.append("removed_requirements")
    if changes:
        drivers.append("change_requests")
    if timeline:
        drivers.append("timeline_impact")
    if budget:
        drivers.append("budget_impact")
    if approval_gap:
        drivers.append("approval_gap")
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or str(getattr(unit, "id", "")),
        "account": _text(metadata.get("account")) or "Unknown account",
        "owner": _text(metadata.get("owner")) or "Unassigned",
        "baseline_scope": _list(metadata.get("baseline_scope")),
        "current_scope": _list(metadata.get("current_scope")),
        "added_requirements": added,
        "removed_requirements": removed,
        "change_requests": changes,
        "timeline_impact_days": timeline,
        "budget_impact": budget,
        "approval_status": approval,
        "approval_gap": approval_gap,
        "drift_severity": severity,
        "drift_score": round(score, 1),
        "drift_drivers": drivers,
        "recommended_mitigation": _mitigation(severity, approval_gap, drivers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "unit_count": len(rows),
        "severity_counts": {severity: sum(1 for row in rows if row["drift_severity"] == severity) for severity in ("high", "medium", "low")},
        "approval_gap_count": sum(1 for row in rows if row["approval_gap"]),
        "total_timeline_impact_days": sum(row["timeline_impact_days"] for row in rows),
    }


def _mitigation_actions(rows: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    if not rows:
        return ["Capture baseline scope, current scope, change requests, and approvals before implementation review."]
    actions = []
    if summary["severity_counts"]["high"]:
        actions.append("Review high drift implementations with delivery, sales, and customer owners before committing new dates.")
    if summary["approval_gap_count"]:
        actions.append("Route open scope changes for approval before additional implementation work.")
    if not actions:
        actions.append("Monitor scope deltas during weekly implementation governance.")
    return actions


def _mitigation(severity: str, approval_gap: bool, drivers: list[str]) -> str:
    if approval_gap:
        return "Obtain explicit approval for scope changes before proceeding."
    if severity == "high":
        return "Rebaseline implementation scope, timeline, and budget."
    if drivers:
        return "Confirm mitigation owners for scope drift drivers."
    return "No immediate scope mitigation required."


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str) and ("," in value or ";" in value):
        return [_text(item) for item in value.replace(";", ",").split(",") if _text(item)]
    text = _text(value)
    return [text] if text else []


def _number(value: Any) -> float | None:
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
