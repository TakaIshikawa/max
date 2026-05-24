"""Feedback signal quality export report."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.feedback_signal_quality_report.v1"
KIND = "max.feedback_signal_quality_report"
DEFAULT_GENERATED_AT = "2026-05-20T00:00:00+00:00"


class FeedbackSignalQualityInput(TypedDict, total=False):
    feedback_id: str
    linked_artifact_id: str
    linked_idea_id: str
    linked_spec_id: str
    outcome: str
    rationale: str
    created_at: str
    follow_up_at: str


def build_feedback_signal_quality_report(
    records: Iterable[FeedbackSignalQualityInput | dict[str, Any]],
    *,
    as_of: str = DEFAULT_GENERATED_AT,
    stale_follow_up_days: int = 14,
    title: str = "Feedback Signal Quality Report",
    generated_at: str = DEFAULT_GENERATED_AT,
) -> dict[str, Any]:
    rows = [_row(raw, index, as_of, stale_follow_up_days) for index, raw in enumerate(records, start=1)]
    rows.sort(key=lambda row: (row["status"] == "complete", row["quality_score"], row["feedback_id"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": _text(generated_at) or DEFAULT_GENERATED_AT,
        "title": _text(title) or "Feedback Signal Quality Report",
        "summary": {
            "total_feedback": len(rows),
            "actionable_feedback": sum(1 for row in rows if row["outcome"] in {"accepted", "rejected", "planned"}),
            "incomplete_feedback": sum(1 for row in rows if row["status"] == "incomplete"),
            "average_quality_score": round(sum(row["quality_score"] for row in rows) / len(rows), 2) if rows else 0.0,
        },
        "feedback_rows": rows,
        "incomplete_feedback": [row for row in rows if row["status"] == "incomplete"],
    }


def render_feedback_signal_quality_report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def render_feedback_signal_quality_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join([f"# {report.get('title') or 'Feedback Signal Quality Report'}", "", "## Summary", "", f"- Feedback: {summary.get('total_feedback', 0)}", f"- Incomplete: {summary.get('incomplete_feedback', 0)}"]).rstrip() + "\n"


def _row(raw: dict[str, Any], index: int, as_of: str, stale_days: int) -> dict[str, Any]:
    outcome = _text(raw.get("outcome")).lower() or "unknown"
    linked = _text(raw.get("linked_artifact_id") or raw.get("linked_idea_id") or raw.get("linked_spec_id"))
    missing = []
    if not linked:
        missing.append("linked_artifact_id")
    if not _text(raw.get("rationale")):
        missing.append("rationale")
    if _is_stale(raw.get("follow_up_at") or raw.get("created_at"), as_of, stale_days) and outcome not in {"accepted", "rejected", "planned"}:
        missing.append("follow_up")
    score = max(0, 100 - len(missing) * 30)
    if outcome in {"unknown", "needs_review"}:
        score = max(0, score - 10)
    return {
        "feedback_id": _text(raw.get("feedback_id") or raw.get("id")) or f"unknown-feedback-{index}",
        "linked_artifact_id": linked,
        "outcome": outcome,
        "quality_score": score,
        "missing_fields": missing,
        "status": "complete" if not missing else "incomplete",
    }


def _is_stale(start: Any, end: Any, days: int) -> bool:
    started = _parse_time(start)
    ended = _parse_time(end)
    if not started or not ended:
        return False
    return (ended - started).days > max(0, days)


def _parse_time(value: Any) -> datetime | None:
    text = _text(value).replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""
