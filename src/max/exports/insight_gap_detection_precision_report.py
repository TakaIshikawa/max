"""Insight gap detection precision export report."""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = "max.insight_gap_detection_precision_report.v1"
KIND = "max.insight_gap_detection_precision_report"
SEVERITY_RANK = {"critical": 0, "warning": 1, "healthy": 2}


def generate_insight_gap_detection_precision_report(
    records: Iterable[dict[str, Any]],
    *,
    warning_precision: float = 0.75,
    critical_precision: float = 0.5,
) -> dict[str, Any]:
    rows = [_row(raw, index, warning_precision, critical_precision) for index, raw in enumerate(records, start=1) if isinstance(raw, dict)]
    rows.sort(key=lambda row: (row["severity_rank"], row["precision"], row["profile"].casefold()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "summary": {
            "profile_count": len(rows),
            "low_precision_count": sum(1 for row in rows if row["status"] != "healthy"),
            "false_positive_total": sum(row["false_positive_gaps"] for row in rows),
            "validated_gap_total": sum(row["validated_gaps"] for row in rows),
        },
        "profile_rows": rows,
    }


def _row(raw: dict[str, Any], index: int, warning_precision: float, critical_precision: float) -> dict[str, Any]:
    detected = _int(raw.get("detected_gaps"))
    validated = _int(raw.get("validated_gaps"))
    false_positive = _int(raw.get("false_positive_gaps"))
    precision = 1.0 if detected == 0 else round(validated / detected, 4)
    false_positive_rate = 0.0 if detected == 0 else round(false_positive / detected, 4)
    status = "critical" if detected > 0 and precision < critical_precision else ("warning" if detected > 0 and precision < warning_precision else "healthy")
    return {
        "profile": _text(raw.get("profile") or raw.get("detector") or raw.get("dimension")) or f"profile-{index}",
        "detected_gaps": detected,
        "validated_gaps": validated,
        "false_positive_gaps": false_positive,
        "window_days": _int(raw.get("window_days")),
        "precision": precision,
        "false_positive_rate": false_positive_rate,
        "status": status,
        "reason": "empty_window" if detected == 0 else ("low_precision" if status != "healthy" else "healthy"),
        "severity_rank": SEVERITY_RANK[status],
    }


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
