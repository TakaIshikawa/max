"""Feedback label disagreement export report."""

from __future__ import annotations

import json
from typing import Any, Iterable

SCHEMA_VERSION = "max.feedback_label_disagreement_report.v1"
KIND = "max.feedback_label_disagreement_report"
DEFAULT_GENERATED_AT = "2026-05-27T00:00:00+00:00"


def build_feedback_label_disagreement_report(records: Iterable[dict[str, Any]], *, title: str = "Feedback Label Disagreement Report", generated_at: str = DEFAULT_GENERATED_AT, escalation_threshold: float = 0.4) -> dict[str, Any]:
    threshold = _clamp(escalation_threshold)
    rows = []
    for raw in records:
        reviewers = _int(raw.get("reviewer_count"))
        disagreements = min(_int(raw.get("disagreement_count")), reviewers) if reviewers else _int(raw.get("disagreement_count"))
        rate = round(disagreements / reviewers, 4) if reviewers else 0.0
        rows.append({"profile": _text(raw.get("profile")) or "unknown-profile", "idea_id": _text(raw.get("idea_id")) or "unknown-idea", "label": _text(raw.get("label")) or "unknown-label", "reviewer_count": reviewers, "disagreement_count": disagreements, "disagreement_rate": rate, "escalate": rate >= threshold})
    rows.sort(key=lambda row: (-row["disagreement_rate"], row["profile"].lower(), row["idea_id"].lower(), row["label"].lower()))
    escalations = [row for row in rows if row["escalate"]]
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT, "title": _text(title) or "Feedback Label Disagreement Report", "summary": {"reviewed_item_count": len(rows), "escalation_count": len(escalations), "average_disagreement_rate": round(sum(row["disagreement_rate"] for row in rows) / len(rows), 4) if rows else 0.0}, "label_disagreements": rows, "escalations": escalations}


def render_feedback_label_disagreement_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_feedback_label_disagreement_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Feedback Label Disagreement Report'}", "", "## Summary", "", f"- Reviewed items: {summary.get('reviewed_item_count', 0)}", f"- Escalations: {summary.get('escalation_count', 0)}"]).rstrip() + "\n"


def _clamp(value: Any) -> float:
    try:
        return min(max(float(value), 0.0), 1.0)
    except (TypeError, ValueError):
        return 0.4


def _int(value: Any) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
