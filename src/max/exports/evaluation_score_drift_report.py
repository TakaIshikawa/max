"""Evaluation score drift export report."""

from __future__ import annotations

import json
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.evaluation_score_drift_report.v1"
KIND = "max.evaluation_score_drift_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class EvaluationScoreDriftInput(TypedDict, total=False):
    unit_id: str
    dimension: str
    previous_score: int | float | str
    current_score: int | float | str


def build_evaluation_score_drift_report(records: Iterable[EvaluationScoreDriftInput | dict[str, Any]], *, drift_threshold: float = 0.1, title: str = "Evaluation Score Drift Report", generated_at: str = DEFAULT_GENERATED_AT) -> dict[str, Any]:
    threshold = max(0.0, float(drift_threshold))
    rows = [_row(raw, index, threshold) for index, raw in enumerate(records, start=1)]
    rows.sort(key=lambda row: (row["status"] == "stable", -row["absolute_drift"], row["unit_id"].lower(), row["dimension"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Evaluation Score Drift Report",
        "drift_threshold": threshold,
        "summary": {
            "evaluation_count": len(rows),
            "average_absolute_drift": round(sum(row["absolute_drift"] for row in rows) / len(rows), 4) if rows else 0.0,
            "maximum_drift": max([row["absolute_drift"] for row in rows] or [0.0]),
            "drifted_unit_count": len({row["unit_id"] for row in rows if row["status"] == "drifted"}),
        },
        "score_drift_rows": rows,
        "drifted_rows": [row for row in rows if row["status"] == "drifted"],
    }


def render_evaluation_score_drift_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_evaluation_score_drift_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Evaluation Score Drift Report'}", "", "## Summary", "", f"- Evaluations: {summary.get('evaluation_count', 0)}", f"- Drifted units: {summary.get('drifted_unit_count', 0)}"]).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int, threshold: float) -> dict[str, Any]:
    previous = _float(raw.get("previous_score"))
    current = _float(raw.get("current_score"))
    drift = round(current - previous, 4)
    absolute = round(abs(drift), 4)
    return {
        "unit_id": _text(raw.get("unit_id") or raw.get("id")) or f"unknown-unit-{index}",
        "dimension": _text(raw.get("dimension")) or "overall",
        "previous_score": previous,
        "current_score": current,
        "absolute_drift": absolute,
        "direction": "up" if drift > 0 else ("down" if drift < 0 else "flat"),
        "status": "drifted" if absolute >= threshold else "stable",
    }


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
