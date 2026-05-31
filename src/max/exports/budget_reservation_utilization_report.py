"""Budget reservation utilization export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.budget_reservation_utilization_report.v1"
KIND = "max.budget_reservation_utilization_report"
DEFAULT_GENERATED_AT = "2026-05-31T00:00:00+00:00"
SEVERITY_RANK = {"critical": 0, "warn": 1, "ok": 2}


def generate_budget_reservation_utilization_report(records: Iterable[dict[str, Any]], *, underutilized_threshold: float = 0.5, generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    rows = [_row(item, index, underutilized_threshold) for index, item in enumerate(records, start=1)]
    rows.sort(key=lambda row: (SEVERITY_RANK[row["severity"]], row["run_id"], row["profile"], row["stage"], row["provider"]))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"reservation_count": len(rows), "underutilized_count": sum(1 for row in rows if row["unused_tokens"] > 0 and row["utilization_ratio"] < underutilized_threshold), "overrun_count": sum(1 for row in rows if row["overrun_tokens"] > 0), "total_unused_tokens": sum(row["unused_tokens"] for row in rows)}, "rows": rows}


def render_budget_reservation_utilization_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_budget_reservation_utilization_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Budget Reservation Utilization Report", "", f"Reservations: {report.get('summary', {}).get('reservation_count', 0)}", ""]
    for row in report.get("rows") or []:
        lines.append(f"- {row['run_id']} / {row['profile']} / {row['stage']} / {row['provider']}: {row['utilization_ratio']} ({row['severity']})")
    return "\n".join(lines).rstrip() + "\n"


def _row(item: dict[str, Any], index: int, threshold: float) -> dict[str, Any]:
    reserved = _int(item.get("reserved_tokens"))
    consumed = _int(item.get("consumed_tokens"))
    ratio = consumed / reserved if reserved else 0.0
    unused = max(0, reserved - consumed)
    overrun = max(0, consumed - reserved)
    severity = "critical" if overrun > 0 else ("warn" if reserved and ratio < threshold else "ok")
    return {"run_id": _text(item.get("run_id") or item.get("id")) or f"run-{index}", "profile": _text(item.get("profile")) or "default", "stage": _text(item.get("stage")) or "unknown", "provider": _text(item.get("provider")) or "unknown", "reserved_tokens": reserved, "consumed_tokens": consumed, "reserved_cost": round(_num(item.get("reserved_cost")), 4), "consumed_cost": round(_num(item.get("consumed_cost")), 4), "utilization_ratio": round(ratio, 4), "unused_tokens": unused, "overrun_tokens": overrun, "severity": severity, "recommended_action": "Increase reservation or cap run usage." if overrun else ("Reduce reservation for this stage." if severity == "warn" else "No action required.")}


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _num(value: Any) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
