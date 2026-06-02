"""Signal source quota burn export report."""

from __future__ import annotations

import json
from typing import Any, Mapping

SCHEMA_VERSION = "max.signal_source_quota_burn_report.v1"
KIND = "max.signal_source_quota_burn_report"


def build_signal_source_quota_burn_report(records: list[Mapping[str, Any]], *, generated_at: str = "2026-06-01T00:00:00+00:00") -> dict[str, Any]:
    rows = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        limit = max(0, _int(record.get("quota_limit") or record.get("limit")))
        consumed = max(0, _int(record.get("consumed_count") or record.get("consumed")))
        remaining = max(0, limit - consumed)
        utilization = round((consumed / limit) * 100, 2) if limit else 0.0
        rows.append({"source": _text(record.get("source")) or "unknown-source", "quota_limit": limit, "consumed_count": consumed, "remaining_count": remaining, "utilization_percent": utilization, "burn_rate": round(float(record.get("burn_rate") or record.get("burn_rate_per_hour") or 0), 4), "reset_at": _text(record.get("reset_at")) or None, "exhaustion_risk": _risk(utilization, remaining)})
    rows.sort(key=lambda row: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[row["exhaustion_risk"]], -row["utilization_percent"], row["source"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": generated_at, "summary": {"source_count": len(rows), "critical_count": sum(1 for row in rows if row["exhaustion_risk"] == "critical")}, "source_rows": rows}


def render_signal_source_quota_burn_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_signal_source_quota_burn_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Signal Source Quota Burn Report", "", "## Sources", ""]
    lines.extend([f"- {row['source']}: {row['utilization_percent']}% used, {row['remaining_count']} remaining ({row['exhaustion_risk']})" for row in report.get("source_rows") or []] or ["- No quota records supplied."])
    return "\n".join(lines).rstrip() + "\n"


def _risk(utilization: float, remaining: int) -> str:
    if remaining == 0 or utilization >= 95:
        return "critical"
    if utilization >= 80:
        return "high"
    if utilization >= 60:
        return "medium"
    return "low"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
