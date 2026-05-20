from __future__ import annotations

import csv
import json
from io import StringIO

import pytest

from max.analysis.feedback_learning_effectiveness import (
    KIND,
    SCHEMA_VERSION,
    FeedbackEvaluationRecord,
    FeedbackOutcomeRecord,
    build_feedback_learning_effectiveness_report,
    render_feedback_learning_effectiveness_report,
)


def test_feedback_learning_effectiveness_tracks_bucket_calibration_and_trend() -> None:
    evaluations = [
        FeedbackEvaluationRecord("a", "yes", "2026-01-05T00:00:00Z"),
        FeedbackEvaluationRecord("b", "strong_yes", "2026-01-06T00:00:00Z"),
        FeedbackEvaluationRecord("c", "no", "2026-01-07T00:00:00Z"),
        FeedbackEvaluationRecord("d", "yes", "2026-02-05T00:00:00Z"),
        FeedbackEvaluationRecord("e", "no", "2026-02-06T00:00:00Z"),
        FeedbackEvaluationRecord("f", "maybe", "2026-02-07T00:00:00Z"),
        FeedbackEvaluationRecord("g", "strong_no", "2026-03-01T00:00:00Z"),
    ]
    feedback = [
        FeedbackOutcomeRecord("a", "rejected", "2026-01-20T00:00:00Z"),
        FeedbackOutcomeRecord("b", "approved", "2026-01-21T00:00:00Z"),
        FeedbackOutcomeRecord("c", "approved", "2026-01-22T00:00:00Z"),
        FeedbackOutcomeRecord("d", "approved", "2026-02-20T00:00:00Z"),
        FeedbackOutcomeRecord("e", "rejected", "2026-02-21T00:00:00Z"),
        FeedbackOutcomeRecord("f", "approved", "2026-02-22T00:00:00Z"),
        FeedbackOutcomeRecord("g", "approved", "2026-03-02T00:00:00Z"),
    ]

    report = build_feedback_learning_effectiveness_report(evaluations, feedback, min_bucket_samples=2)
    repeated = build_feedback_learning_effectiveness_report(evaluations, feedback, min_bucket_samples=2)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["rows"] == [
        {
            "bucket": "2026-01",
            "evaluated_count": 3,
            "approval_rate": 0.6667,
            "false_positive_count": 1,
            "false_negative_count": 1,
            "calibration_band": "poor",
        },
        {
            "bucket": "2026-02",
            "evaluated_count": 3,
            "approval_rate": 0.6667,
            "false_positive_count": 0,
            "false_negative_count": 0,
            "calibration_band": "aligned",
        },
        {
            "bucket": "2026-03",
            "evaluated_count": 1,
            "approval_rate": 1.0,
            "false_positive_count": 0,
            "false_negative_count": 1,
            "calibration_band": "insufficient_data",
        },
    ]
    assert report["summary"]["trend"] == "improving"
    assert report["summary"]["improving_bucket_count"] == 1
    assert report["summary"]["degrading_bucket_count"] == 1
    assert report["summary"]["insufficient_data_bucket_count"] == 1


def test_feedback_learning_effectiveness_accepts_mapping_records_and_renders() -> None:
    evaluations = [
        {"buildable_unit_id": "b", "recommendation": "yes", "evaluated_at": "2026-01-01"},
        {"buildable_unit_id": "a", "recommendation": "no", "evaluated_at": "2026-01-01"},
    ]
    feedback = [
        {"buildable_unit_id": "b", "outcome": "rejected", "created_at": "2026-01-02"},
        {"buildable_unit_id": "a", "outcome": "approved", "created_at": "2026-01-02"},
    ]
    report = build_feedback_learning_effectiveness_report(evaluations, feedback, bucket="day", min_bucket_samples=1)

    assert json.loads(render_feedback_learning_effectiveness_report(report, fmt="json")) == report

    markdown = render_feedback_learning_effectiveness_report(report, fmt="markdown")
    assert markdown.startswith("# Feedback Learning Effectiveness")
    assert "| `2026-01-02` | 2 | 0.500 | 1 | 1 | poor |" in markdown

    rendered_csv = render_feedback_learning_effectiveness_report(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "bucket,evaluated_count,approval_rate,false_positive_count,"
        "false_negative_count,calibration_band"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert rows[0]["bucket"] == "2026-01-02"
    assert rows[0]["false_positive_count"] == "1"

    with pytest.raises(ValueError, match="Unsupported feedback learning effectiveness report format: yaml"):
        render_feedback_learning_effectiveness_report(report, fmt="yaml")


def test_feedback_learning_effectiveness_validates_arguments() -> None:
    with pytest.raises(ValueError, match="bucket must be day or month"):
        build_feedback_learning_effectiveness_report([], [], bucket="week")
    with pytest.raises(ValueError, match="min_bucket_samples must be at least 1"):
        build_feedback_learning_effectiveness_report([], [], min_bucket_samples=0)
    with pytest.raises(ValueError, match="improvement_threshold must be non-negative"):
        build_feedback_learning_effectiveness_report([], [], improvement_threshold=-0.1)
