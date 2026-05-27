"""Feedback weight shift export report."""

from __future__ import annotations

import json
from typing import Any, Iterable


def build_feedback_weight_shift_report(records: Iterable[dict[str, Any]], *, watch_threshold: float = 0.1, review_threshold: float = 0.25) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        baseline = _float(raw.get("baseline_weight") or raw.get("baseline"))
        current = _float(raw.get("current_weight") or raw.get("current"))
        proposed = _float(raw.get("proposed_weight") if raw.get("proposed_weight") is not None else raw.get("proposed"))
        target = proposed if proposed else current
        absolute = round(target - baseline, 4)
        relative = round(absolute / baseline, 4) if baseline else 0.0
        magnitude = abs(relative or absolute)
        status = "review_required" if magnitude >= review_threshold else "watch" if magnitude >= watch_threshold else "stable"
        rows.append({"dimension": _text(raw.get("dimension")) or "unknown-dimension", "baseline_weight": baseline, "current_weight": current, "proposed_weight": target, "approval_evidence_count": _int(raw.get("approval_evidence_count") or raw.get("approvals")), "rejection_evidence_count": _int(raw.get("rejection_evidence_count") or raw.get("rejections")), "absolute_delta": absolute, "relative_delta": relative, "shift_status": status, "review_recommendation": _action(status)})
    rows.sort(key=lambda row: ({"review_required": 0, "watch": 1, "stable": 2}[row["shift_status"]], row["dimension"].lower()))
    return rows


def render_feedback_weight_shift_report_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(rows, indent=2, sort_keys=True, default=str) + "\n"


def render_feedback_weight_shift_report_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Feedback Weight Shift Report", "", "| Dimension | Baseline | Current | Proposed | Absolute delta | Relative delta | Status |", "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    for row in rows:
        lines.append(f"| {row['dimension']} | {row['baseline_weight']} | {row['current_weight']} | {row['proposed_weight']} | {row['absolute_delta']} | {row['relative_delta']} | {row['shift_status']} |")
    return "\n".join(lines).rstrip() + "\n"


def _action(status: str) -> str:
    return {"review_required": "Review weight change before applying.", "watch": "Monitor next calibration cycle.", "stable": "No review required."}[status]


def _float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
