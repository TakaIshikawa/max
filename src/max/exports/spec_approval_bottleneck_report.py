"""Spec approval bottleneck export report."""

from __future__ import annotations

import json
from collections import defaultdict
from statistics import median
from typing import Any, Iterable

SCHEMA_VERSION = "max.spec_approval_bottleneck_report.v1"
KIND = "max.spec_approval_bottleneck_report"


def generate_spec_approval_bottleneck_report(records: Iterable[dict[str, Any]], *, sla_hours: float = 48.0, title: str = "Spec Approval Bottleneck Report") -> dict[str, Any]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(lambda: {"pending": 0, "approved": 0, "rejected": 0, "waits": [], "overdue": 0})
    for raw in records:
        if not isinstance(raw, dict):
            continue
        key = (_text(raw.get("reviewer") or raw.get("owner")) or "unassigned", _text(raw.get("spec_type") or raw.get("type")) or "unknown-spec-type", _text(raw.get("approval_stage") or raw.get("stage")) or "unknown-stage")
        group = groups[key]
        status = _text(raw.get("status") or raw.get("outcome")).lower()
        wait = _hours(raw.get("wait_hours") or raw.get("age_hours") or raw.get("pending_hours"))
        group["waits"].append(wait)
        if status in {"approved", "accepted"}:
            group["approved"] += 1
        elif status in {"rejected", "declined"}:
            group["rejected"] += 1
        else:
            group["pending"] += 1
        if status not in {"approved", "accepted", "rejected", "declined"} and wait > sla_hours:
            group["overdue"] += 1
    rows = [_row(*key, group, sla_hours) for key, group in groups.items()]
    rows.sort(key=lambda r: (-r["overdue_count"], -r["pending_count"], -r["median_wait_hours"], r["reviewer"].lower(), r["spec_type"].lower(), r["approval_stage"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "title": title, "summary": {"row_count": len(rows), "pending_count": sum(r["pending_count"] for r in rows), "overdue_count": sum(r["overdue_count"] for r in rows), "sla_hours": sla_hours}, "rows": rows}


def render_spec_approval_bottleneck_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_spec_approval_bottleneck_report_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report.get('title') or 'Spec Approval Bottleneck Report'}", "", "## Summary", "", f"- Overdue: {report.get('summary', {}).get('overdue_count', 0)}", "", "## Bottleneck Rows", ""]
    rows = report.get("rows") or []
    lines.extend([f"- {r['reviewer']} / {r['spec_type']} / {r['approval_stage']}: {r['pending_count']} pending, {r['overdue_count']} overdue" for r in rows] or ["- No approval bottlenecks detected."])
    return "\n".join(lines).rstrip() + "\n"


def _row(reviewer: str, spec_type: str, stage: str, group: dict[str, Any], sla: float) -> dict[str, Any]:
    med = round(float(median(group["waits"])), 2) if group["waits"] else 0.0
    return {"reviewer": reviewer, "spec_type": spec_type, "approval_stage": stage, "pending_count": group["pending"], "approved_count": group["approved"], "rejected_count": group["rejected"], "median_wait_hours": med, "overdue_count": group["overdue"], "severity": "high" if group["overdue"] else "medium" if group["pending"] else "low", "recommended_action": "Escalate overdue approvals and rebalance reviewer queue." if group["overdue"] else "Monitor reviewer throughput against SLA.", "sla_hours": sla}


def _hours(value: Any) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
