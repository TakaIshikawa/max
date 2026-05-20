"""Feedback outcome calibration report export."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable, TypedDict

SCHEMA_VERSION = "max.feedback_outcome_calibration.v1"
KIND = "max.feedback_outcome_calibration"


class FeedbackOutcomeCalibrationInput(TypedDict, total=False):
    idea_id: str
    idea: str
    name: str
    predicted_recommendation: str
    predicted_score: float
    feedback_outcome: str
    outcome_score: float
    success_score: float
    feedback_at: str
    reason: str


def build_feedback_outcome_calibration_report(
    rows: Iterable[FeedbackOutcomeCalibrationInput | dict[str, Any]],
    *,
    title: str = "Feedback Outcome Calibration Report",
    mismatch_threshold: float = 0.2,
    top_reason_limit: int = 5,
) -> dict[str, Any]:
    records = _normalize_records(rows, mismatch_threshold=mismatch_threshold)
    matched = [record for record in records if record["has_feedback_outcome"]]
    mismatches = [record for record in matched if record["mismatch"]]
    mismatches.sort(key=_mismatch_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Feedback Outcome Calibration Report",
        "mismatch_threshold": mismatch_threshold,
        "summary": {
            "row_count": len(records),
            "matched_outcome_count": len(matched),
            "mismatch_count": len(mismatches),
            "average_prediction_error": _average_error(matched),
        },
        "calibration_buckets": _calibration_buckets(records),
        "top_mismatch_reasons": _top_mismatch_reasons(mismatches, limit=top_reason_limit),
        "mismatches": mismatches,
        "records": records,
    }


def render_feedback_outcome_calibration_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Feedback Outcome Calibration Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Rows: {summary.get('row_count', 0)}",
        f"- Matched outcomes: {summary.get('matched_outcome_count', 0)}",
        f"- Mismatches: {summary.get('mismatch_count', 0)}",
        f"- Average prediction error: {summary.get('average_prediction_error', 0.0)}",
        "",
        "## Calibration Buckets",
        "",
    ]
    buckets = report.get("calibration_buckets") or []
    if buckets:
        for bucket in buckets:
            lines.extend(
                [
                    f"### {bucket['predicted_recommendation']}",
                    "",
                    f"- Records: {bucket['record_count']}",
                    f"- Matched outcomes: {bucket['matched_outcome_count']}",
                    f"- Average predicted score: {bucket['average_predicted_score']}",
                    f"- Average outcome score: {bucket['average_outcome_score']}",
                    f"- Average prediction error: {bucket['average_prediction_error']}",
                    "",
                ]
            )
    else:
        lines.extend(["- No feedback outcome rows were supplied.", ""])

    lines.extend(["## Mismatches", ""])
    mismatches = report.get("mismatches") or []
    if mismatches:
        for mismatch in mismatches:
            lines.extend(
                [
                    f"### {mismatch['idea_id']} - {mismatch['idea']}",
                    "",
                    f"- Predicted: {mismatch['predicted_recommendation']} ({mismatch['predicted_score']})",
                    f"- Outcome: {mismatch['feedback_outcome']} ({mismatch['outcome_score']})",
                    f"- Prediction error: {mismatch['prediction_error']}",
                    f"- Feedback at: {mismatch['feedback_at'] or 'Unspecified'}",
                    f"- Reason: {mismatch['reason']}",
                    "",
                ]
            )
    else:
        lines.append("- No feedback outcome mismatches were detected.")
    return "\n".join(lines).rstrip() + "\n"


def render_feedback_outcome_calibration_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_records(
    rows: Iterable[FeedbackOutcomeCalibrationInput | dict[str, Any]],
    *,
    mismatch_threshold: float,
) -> list[dict[str, Any]]:
    records = []
    for index, raw in enumerate(rows):
        idea_id = _text(raw.get("idea_id") or raw.get("idea") or raw.get("name") or f"idea-{index + 1}")
        predicted_recommendation = _label(raw.get("predicted_recommendation") or raw.get("recommendation") or "unknown")
        feedback_outcome = _label(raw.get("feedback_outcome") or raw.get("outcome") or "unmatched")
        has_feedback_outcome = feedback_outcome != "unmatched"
        predicted_score = _score(raw.get("predicted_score"), default=_score_for_label(predicted_recommendation))
        outcome_score = _score(raw.get("outcome_score", raw.get("success_score")), default=_score_for_label(feedback_outcome))
        prediction_error = round(abs(predicted_score - outcome_score), 4) if has_feedback_outcome else 0.0
        direction_match = _direction(predicted_recommendation) == _direction(feedback_outcome)
        mismatch = has_feedback_outcome and (prediction_error >= mismatch_threshold or not direction_match)
        records.append(
            {
                "idea_id": idea_id,
                "idea": _text(raw.get("idea") or raw.get("name") or idea_id),
                "predicted_recommendation": predicted_recommendation,
                "predicted_score": predicted_score,
                "feedback_outcome": feedback_outcome,
                "outcome_score": outcome_score,
                "has_feedback_outcome": has_feedback_outcome,
                "prediction_error": prediction_error,
                "mismatch": mismatch,
                "feedback_at": _text(raw.get("feedback_at")),
                "reason": _text(raw.get("reason") or "Unspecified reason"),
            }
        )
    records.sort(key=_record_sort_key)
    return records


def _calibration_buckets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["predicted_recommendation"]].append(record)
    buckets = []
    for recommendation, items in grouped.items():
        matched = [item for item in items if item["has_feedback_outcome"]]
        buckets.append(
            {
                "predicted_recommendation": recommendation,
                "record_count": len(items),
                "matched_outcome_count": len(matched),
                "mismatch_count": sum(1 for item in matched if item["mismatch"]),
                "average_predicted_score": _average([item["predicted_score"] for item in items]),
                "average_outcome_score": _average([item["outcome_score"] for item in matched]),
                "average_prediction_error": _average([item["prediction_error"] for item in matched]),
            }
        )
    buckets.sort(key=lambda bucket: (-bucket["matched_outcome_count"], bucket["predicted_recommendation"].lower()))
    return buckets


def _top_mismatch_reasons(mismatches: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    counts = Counter(mismatch["reason"] for mismatch in mismatches)
    rows = [{"reason": reason, "count": count} for reason, count in counts.items()]
    rows.sort(key=lambda row: (-row["count"], row["reason"].lower()))
    return rows[: max(limit, 0)]


def _average_error(records: list[dict[str, Any]]) -> float:
    return _average([record["prediction_error"] for record in records])


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _mismatch_sort_key(record: dict[str, Any]) -> tuple[float, str, str, str]:
    return (
        -record["prediction_error"],
        record["feedback_at"] or "",
        record["idea_id"].lower(),
        record["predicted_recommendation"].lower(),
    )


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (record["idea_id"].lower(), record["feedback_at"] or "", record["predicted_recommendation"].lower())


def _direction(label: str) -> str:
    if label in {"approve", "approved", "success", "successful", "won", "positive", "accepted"}:
        return "positive"
    if label in {"reject", "rejected", "failure", "failed", "lost", "negative"}:
        return "negative"
    if label in {"monitor", "partial", "neutral", "mixed"}:
        return "neutral"
    return label


def _score_for_label(label: str) -> float:
    direction = _direction(label)
    if direction == "positive":
        return 1.0
    if direction == "negative":
        return 0.0
    if direction == "neutral":
        return 0.5
    return 0.0


def _score(value: Any, *, default: float) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return default


def _label(value: Any) -> str:
    return _text(value).lower().replace(" ", "_") or "unknown"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
