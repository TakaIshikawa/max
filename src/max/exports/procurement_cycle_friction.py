"""Procurement cycle friction export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.procurement_cycle_friction.v1"
KIND = "max.procurement_cycle_friction"

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def build_procurement_cycle_friction_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    rows = [_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (_SEVERITY_ORDER[row["elapsed_time_severity"]], -row["elapsed_days"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "procurement_cycle_friction", "domain_filter": domain},
        "cycle_rows": rows,
        "summary": _summary(rows),
        "friction_points": [point for row in rows for point in row["friction_points"]],
        "acceleration_actions": _recommendations(rows),
    }


def render_procurement_cycle_friction_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_procurement_cycle_friction_markdown(report: dict[str, Any]) -> str:
    lines = ["# Procurement Cycle Friction", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Cycles", ""]
    if report.get("cycle_rows"):
        lines.extend(["| Idea | Account | Stage | Elapsed | Severity | Friction | Blockers | Action |", "|------|---------|-------|---------|----------|----------|----------|--------|"])
        for row in report["cycle_rows"]:
            lines.append(
                f"| {_md(row['title'])} | {_md(row['account'])} | {_md(row['cycle_stage_summary']['current_stage'])} | "
                f"{row['elapsed_days']} | {row['elapsed_time_severity']} | "
                f"{_md(', '.join(point['point'] for point in row['friction_points']) or 'None')} | "
                f"{_md(', '.join(row['stakeholder_blockers']) or 'None')} | {_md(row['recommended_action'])} |"
            )
    else:
        lines.append("- No procurement cycle friction metadata available.")
    lines.extend(["", "## Acceleration Actions", ""])
    lines.extend(f"- {item}" for item in report.get("acceleration_actions", []))
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    approval_steps = _list(metadata.get("approval_steps") or metadata.get("procurement_steps"))
    completed_steps = _list(metadata.get("completed_steps") or metadata.get("approved_steps"))
    stalled_artifacts = _list(metadata.get("stalled_artifacts") or metadata.get("missing_artifacts"))
    buyer_roles = _list(metadata.get("buyer_roles") or metadata.get("stakeholders"))
    legal_blockers = _list(metadata.get("legal_blockers") or metadata.get("legal_security_blockers"))
    security_blockers = _list(metadata.get("security_blockers"))
    stakeholder_blockers = legal_blockers + security_blockers + _list(metadata.get("stakeholder_blockers"))
    elapsed = _int(metadata.get("elapsed_days") or metadata.get("days_in_procurement"), 0)
    stage = _text(metadata.get("current_stage") or metadata.get("stage") or _current_stage(approval_steps, completed_steps))
    severity = _severity(elapsed, stalled_artifacts, stakeholder_blockers)
    friction = _friction_points(stalled_artifacts, stakeholder_blockers, approval_steps, completed_steps, elapsed)
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "title": _text(getattr(unit, "title", "")) or "Untitled",
        "account": _text(metadata.get("account") or metadata.get("customer") or metadata.get("segment") or "Unknown"),
        "cycle_stage_summary": {
            "current_stage": stage or "unknown",
            "approval_steps": approval_steps,
            "completed_steps": completed_steps,
            "remaining_steps": [step for step in approval_steps if step not in completed_steps],
        },
        "stalled_artifacts": stalled_artifacts,
        "buyer_roles": buyer_roles,
        "stakeholder_blockers": stakeholder_blockers,
        "elapsed_days": elapsed,
        "elapsed_time_severity": severity,
        "friction_points": friction,
        "recommended_action": _action(severity, stalled_artifacts, stakeholder_blockers),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cycle_count": len(rows),
        "average_elapsed_days": round(sum(row["elapsed_days"] for row in rows) / len(rows), 1) if rows else 0.0,
        "severity_counts": {severity: sum(1 for row in rows if row["elapsed_time_severity"] == severity) for severity in _SEVERITY_ORDER},
        "blocked_cycle_count": sum(1 for row in rows if row["stakeholder_blockers"] or row["stalled_artifacts"]),
    }


def _recommendations(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["Capture approval steps, buyer roles, stalled artifacts, blockers, and elapsed procurement time."]
    recommendations = []
    if any(row["elapsed_time_severity"] == "critical" for row in rows):
        recommendations.append("Escalate critical procurement cycles with executive sponsor and buyer procurement lead.")
    if any(row["stalled_artifacts"] for row in rows):
        recommendations.append("Assign owners to stalled artifacts and confirm acceptance criteria.")
    if any(row["stakeholder_blockers"] for row in rows):
        recommendations.append("Run legal and security blocker review with dated closure actions.")
    return recommendations or ["Maintain procurement cadence and update elapsed-time risk weekly."]


def _friction_points(stalled: list[str], blockers: list[str], steps: list[str], completed: list[str], elapsed: int) -> list[dict[str, str]]:
    points = [{"point": artifact, "type": "stalled artifact"} for artifact in stalled]
    points.extend({"point": blocker, "type": "stakeholder blocker"} for blocker in blockers)
    remaining = [step for step in steps if step not in completed]
    if remaining:
        points.append({"point": remaining[0], "type": "pending approval step"})
    if elapsed > 45:
        points.append({"point": f"{elapsed} days elapsed", "type": "elapsed time"})
    return points


def _severity(elapsed: int, stalled: list[str], blockers: list[str]) -> str:
    score = elapsed + len(stalled) * 12 + len(blockers) * 18
    if score >= 90:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _action(severity: str, stalled: list[str], blockers: list[str]) -> str:
    if blockers:
        return f"Resolve blocker with accountable stakeholder: {blockers[0]}."
    if stalled:
        return f"Unblock stalled artifact: {stalled[0]}."
    if severity in {"critical", "high"}:
        return "Escalate procurement timeline and reset approval date."
    return "Keep buyer roles aligned on the next approval step."


def _current_stage(steps: list[str], completed: list[str]) -> str:
    for step in steps:
        if step not in completed:
            return step
    return "complete" if steps else ""


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    return [_text(item) for item in value if _text(item)] if isinstance(value, (list, tuple, set)) else [_text(value)]


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
