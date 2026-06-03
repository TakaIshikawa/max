"""Profile cadence adherence export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_cadence_adherence_report.v1"
KIND = "max.profile_cadence_adherence_report"
SEVERITY_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def generate_profile_cadence_adherence_report(
    records: Iterable[dict[str, Any]],
    *,
    warning_adherence_rate: float = 0.9,
    critical_adherence_rate: float = 0.75,
) -> dict[str, Any]:
    rows = [_row(raw, index, warning_adherence_rate, critical_adherence_rate) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["adherence_rate"], row["profile"].casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": _summary(rows), "profile_rows": rows}


def render_profile_cadence_adherence_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def render_profile_cadence_adherence_report_markdown(report: dict[str, Any]) -> str:
    lines = ["# Profile Cadence Adherence Report", "", f"- Profiles: {report['summary']['profile_count']}", f"- Nonadherent profiles: {report['summary']['nonadherent_profile_count']}", ""]
    for row in report.get("profile_rows", []):
        lines.append(f"- {row['profile']}: {row['status']} ({row['adherence_rate']:.4f})")
    return "\n".join(lines)


def _row(raw: dict[str, Any], index: int, warning: float, critical: float) -> dict[str, Any]:
    expected = _int(raw.get("expected_runs"))
    completed = _int(raw.get("completed_runs"))
    missed = _int(raw.get("missed_runs"))
    late = _int(raw.get("late_runs"))
    rate = round(completed / expected, 4) if expected else 1.0
    status = "critical" if rate < critical else "warning" if rate < warning else "healthy"
    return {"profile": _text(raw.get("profile")) or f"profile-{index}", "expected_runs": expected, "completed_runs": completed, "missed_runs": missed, "late_runs": late, "window_days": _int(raw.get("window_days")), "adherence_rate": rate, "status": status, "severity_rank": SEVERITY_RANK[status]}


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"profile_count": len(rows), "nonadherent_profile_count": sum(1 for row in rows if row["status"] != "healthy"), "average_adherence_rate": round(sum(row["adherence_rate"] for row in rows) / len(rows), 4) if rows else 0.0, "total_missed_runs": sum(row["missed_runs"] for row in rows), "total_late_runs": sum(row["late_runs"] for row in rows)}


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
