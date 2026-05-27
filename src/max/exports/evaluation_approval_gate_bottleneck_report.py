"""Evaluation approval gate bottleneck export report."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.evaluation_approval_gate_bottleneck_report.v1"
KIND = "max.evaluation_approval_gate_bottleneck_report"
DEFAULT_AS_OF = "2026-05-27T00:00:00+00:00"


def build_evaluation_approval_gate_bottleneck_report(records: Iterable[dict[str, Any]], *, threshold_hours: float = 24.0, as_of: str = DEFAULT_AS_OF) -> dict[str, Any]:
    now = _dt(as_of) or datetime(2026, 5, 27, tzinfo=timezone.utc)
    threshold = max(0.0, float(threshold_hours))
    gates = [_gate(raw, index, now, threshold) for index, raw in enumerate(records, start=1)]
    gates.sort(key=lambda row: (-row["wait_hours"], row["gate"].casefold(), row["reviewer"].casefold(), row["id"].casefold()))
    reviewer_totals = _totals(gates, "reviewer")
    profile_totals = _totals(gates, "profile")
    overdue = [row for row in gates if row["overdue"]]
    bottleneck = [row for row in gates if row["wait_hours"] == max([item["wait_hours"] for item in gates] or [0.0]) and row["wait_hours"] > 0]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "as_of": _text(as_of) or DEFAULT_AS_OF,
        "threshold_hours": threshold,
        "summary": {"gate_count": len(gates), "open_gate_count": sum(1 for row in gates if row["status"] == "open"), "overdue_gate_count": len(overdue), "average_wait_hours": round(sum(row["wait_hours"] for row in gates) / len(gates), 2) if gates else 0.0},
        "gates": gates,
        "reviewer_totals": reviewer_totals,
        "profile_totals": profile_totals,
        "overdue_gates": overdue,
        "bottleneck_gates": bottleneck,
    }


def render_evaluation_approval_gate_bottleneck_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_evaluation_approval_gate_bottleneck_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Evaluation Approval Gate Bottleneck Report", "", "| Gate | Reviewer | Profile | Wait hours | Overdue |", "| --- | --- | --- | ---: | --- |"]
    for row in report.get("gates", []):
        lines.append(f"| {row['gate']} | {row['reviewer']} | {row['profile']} | {row['wait_hours']} | {row['overdue']} |")
    return "\n".join(lines).rstrip() + "\n"


def _gate(raw: dict[str, Any], index: int, as_of: datetime, threshold: float) -> dict[str, Any]:
    submitted = _dt(raw.get("submitted_at"))
    reviewed = _dt(raw.get("reviewed_at"))
    wait = raw.get("wait_hours")
    if wait is None and submitted:
        wait = ((reviewed or as_of) - submitted).total_seconds() / 3600
    wait_hours = round(max(0.0, _float(wait)), 2)
    status = _text(raw.get("status")) or ("closed" if reviewed else "open")
    return {"id": _text(raw.get("id") or raw.get("gate_id")) or f"gate-{index}", "gate": _text(raw.get("gate") or raw.get("name")) or "evaluation approval", "reviewer": _text(raw.get("reviewer") or raw.get("owner")) or "unassigned", "profile": _text(raw.get("profile")) or "default", "submitted_at": _text(raw.get("submitted_at")), "reviewed_at": _text(raw.get("reviewed_at")), "status": status, "wait_hours": wait_hours, "overdue": wait_hours > threshold}


def _totals(gates: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in gates:
        item = grouped.setdefault(row[key], {key: row[key], "gate_count": 0, "overdue_gate_count": 0, "total_wait_hours": 0.0})
        item["gate_count"] += 1
        item["overdue_gate_count"] += int(row["overdue"])
        item["total_wait_hours"] = round(item["total_wait_hours"] + row["wait_hours"], 2)
    return sorted(grouped.values(), key=lambda item: (-item["total_wait_hours"], item[key].casefold()))


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
