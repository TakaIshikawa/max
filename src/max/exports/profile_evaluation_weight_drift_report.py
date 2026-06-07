"""Profile evaluation weight drift export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.profile_evaluation_weight_drift_report.v1"
KIND = "max.profile_evaluation_weight_drift_report"


def generate_profile_evaluation_weight_drift_report(records: Iterable[dict[str, Any]], *, warning_delta_threshold: float = 0.1, critical_delta_threshold: float = 0.25) -> dict[str, Any]:
    rows = []
    for raw in records:
        baseline = _float(raw.get("baseline_weight") or raw.get("baseline"))
        current = _float(raw.get("current_weight") or raw.get("current"))
        absolute_delta = round(abs(current - baseline), 4)
        percent_delta = round(absolute_delta / abs(baseline), 4) if baseline else 0.0
        status = "critical" if absolute_delta >= critical_delta_threshold else "warning" if absolute_delta >= warning_delta_threshold else "ok"
        rows.append({"profile": _text(raw.get("profile")) or "unknown-profile", "dimension": _text(raw.get("dimension")) or "unknown-dimension", "baseline_weight": baseline, "current_weight": current, "absolute_delta": absolute_delta, "percent_delta": percent_delta, "status": status})
    rows.sort(key=lambda row: ({"critical": 0, "warning": 1, "ok": 2}[row["status"]], row["profile"].lower(), row["dimension"].lower()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "summary": {"row_count": len(rows), "warning_count": sum(1 for row in rows if row["status"] == "warning"), "critical_count": sum(1 for row in rows if row["status"] == "critical"), "warning_delta_threshold": warning_delta_threshold, "critical_delta_threshold": critical_delta_threshold}, "rows": rows}


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
