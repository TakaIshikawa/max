"""Idea aging SLA export report."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.idea_aging_sla_report.v1"
KIND = "max.idea_aging_sla_report"


def build_idea_aging_sla_report_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_row(unit, today) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    rows.sort(key=lambda row: (not row["overdue"], -row["age_days"], row["stage"].lower(), row["title"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "idea_aging_sla_report", "domain_filter": domain},
        "summary": _summary(rows),
        "stage_rows": _stage_rows(rows),
        "idea_rows": rows,
        "overdue_idea_rows": [row for row in rows if row["overdue"]],
    }


def render_idea_aging_sla_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def render_idea_aging_sla_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = ["# Idea Aging SLA Report", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Summary", "", f"- Ideas: {summary.get('idea_count', 0)}", f"- Overdue: {summary.get('overdue_count', 0)}", f"- Oldest age days: {summary.get('oldest_age_days', 0)}", "", "## Overdue Ideas", ""]
    overdue = report.get("overdue_idea_rows") or []
    if overdue:
        lines.extend(["| Idea | Stage | Owner | Age | SLA | Action |", "|------|-------|-------|-----|-----|--------|"])
        for row in overdue:
            lines.append(f"| {_md(row['title'])} | {_md(row['stage'])} | {_md(row['owner'])} | {row['age_days']} | {row['sla_days']} | {_md(row['recommended_next_action'])} |")
    else:
        lines.append("- No overdue ideas.")
    lines.extend(["", "## Stage Summary", ""])
    for row in report.get("stage_rows") or []:
        lines.append(f"- {row['stage']}: {row['idea_count']} ideas, {row['overdue_count']} overdue")
    return "\n".join(lines).rstrip() + "\n"


def _row(unit: Any, today: date) -> dict[str, Any]:
    metadata = _metadata(unit)
    created = _parse_date(metadata.get("idea_created_at") or metadata.get("created_at") or metadata.get("submitted_at"))
    age = max(0, (today - created).days) if created else 0
    stage = _text(metadata.get("stage") or metadata.get("idea_stage")) or "intake"
    sla_days = _int(metadata.get("sla_days") or metadata.get("target_sla_days"), _default_sla(stage))
    overdue = age > sla_days
    return {
        "idea_id": _text(metadata.get("idea_id") or getattr(unit, "id", "")) or "unknown-idea",
        "title": _text(metadata.get("title") or getattr(unit, "title", "")) or "Untitled idea",
        "created_at": created.isoformat() if created else "",
        "age_days": age,
        "stage": stage,
        "owner": _text(metadata.get("owner")) or "Unassigned",
        "sla_days": sla_days,
        "overdue": overdue,
        "recommended_next_action": _action(stage, overdue),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"idea_count": len(rows), "overdue_count": sum(1 for row in rows if row["overdue"]), "oldest_age_days": max([row["age_days"] for row in rows] or [0])}


def _stage_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stages = sorted({row["stage"] for row in rows}, key=str.casefold)
    return [{"stage": stage, "idea_count": sum(1 for row in rows if row["stage"] == stage), "overdue_count": sum(1 for row in rows if row["stage"] == stage and row["overdue"]), "oldest_age_days": max([row["age_days"] for row in rows if row["stage"] == stage] or [0])} for stage in stages]


def _default_sla(stage: str) -> int:
    return {"intake": 14, "discovery": 30, "review": 21, "approved": 45, "backlog": 60}.get(stage.lower(), 30)


def _action(stage: str, overdue: bool) -> str:
    if overdue:
        return f"Escalate {stage} owner and refresh decision date"
    return "Continue SLA monitoring"


def _parse_date(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _metadata(unit: Any) -> dict[str, Any]:
    metadata = getattr(unit, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def _int(value: Any, default: int) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
