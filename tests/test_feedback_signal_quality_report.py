from __future__ import annotations

import json

from max.exports.feedback_signal_quality_report import (
    KIND,
    build_feedback_signal_quality_report,
    render_feedback_signal_quality_report_json,
)


def test_feedback_signal_quality_scores_complete_and_incomplete() -> None:
    report = build_feedback_signal_quality_report(
        [
            {"feedback_id": "f1", "linked_idea_id": "i1", "outcome": "accepted", "rationale": "clear"},
            {"feedback_id": "f2", "outcome": "needs_review", "created_at": "2026-05-01T00:00:00+00:00"},
        ],
        as_of="2026-05-20T00:00:00+00:00",
    )

    assert report["kind"] == KIND
    assert report["summary"]["total_feedback"] == 2
    assert report["summary"]["actionable_feedback"] == 1
    assert report["summary"]["incomplete_feedback"] == 1
    assert report["summary"]["average_quality_score"] == 50.0
    assert report["feedback_rows"][0]["feedback_id"] == "f2"
    assert report["feedback_rows"][0]["missing_fields"] == ["linked_artifact_id", "rationale", "follow_up"]
    assert json.loads(render_feedback_signal_quality_report_json(report))["summary"]["total_feedback"] == 2


def test_feedback_signal_quality_defaults_missing_fields() -> None:
    report = build_feedback_signal_quality_report([{}])

    assert report["feedback_rows"][0]["feedback_id"] == "unknown-feedback-1"
    assert report["feedback_rows"][0]["status"] == "incomplete"
