from __future__ import annotations

import json

from max.exports.feedback_outcome_calibration import (
    KIND,
    SCHEMA_VERSION,
    build_feedback_outcome_calibration_report,
    render_feedback_outcome_calibration_json,
    render_feedback_outcome_calibration_markdown,
)


def test_feedback_outcome_calibration_mixed_outcomes_and_buckets() -> None:
    report = build_feedback_outcome_calibration_report(
        [
            {
                "idea_id": "checkout",
                "name": "Fast checkout",
                "predicted_recommendation": "approve",
                "predicted_score": 0.9,
                "feedback_outcome": "success",
                "outcome_score": 0.8,
                "feedback_at": "2026-05-10",
                "reason": "conversion lift",
            },
            {
                "idea_id": "pricing",
                "name": "Pricing guardrails",
                "predicted_recommendation": "approve",
                "predicted_score": 0.85,
                "feedback_outcome": "failed",
                "success_score": 0.1,
                "feedback_at": "2026-05-09",
                "reason": "discount leakage",
            },
            {
                "idea_id": "search",
                "predicted_recommendation": "monitor",
                "predicted_score": 0.55,
                "feedback_outcome": "partial",
                "outcome_score": 0.5,
                "reason": "mixed signal",
            },
        ],
        mismatch_threshold=0.2,
    )

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert report["summary"] == {
        "row_count": 3,
        "matched_outcome_count": 3,
        "mismatch_count": 1,
        "average_prediction_error": 0.3,
    }
    assert report["calibration_buckets"][0]["predicted_recommendation"] == "approve"
    assert report["calibration_buckets"][0]["mismatch_count"] == 1
    assert report["top_mismatch_reasons"] == [{"reason": "discount leakage", "count": 1}]


def test_feedback_outcome_calibration_normalizes_missing_fields() -> None:
    report = build_feedback_outcome_calibration_report([{"name": "Untitled", "predicted_recommendation": "reject"}])

    assert report["records"] == [
        {
            "idea_id": "Untitled",
            "idea": "Untitled",
            "predicted_recommendation": "reject",
            "predicted_score": 0.0,
            "feedback_outcome": "unmatched",
            "outcome_score": 0.0,
            "has_feedback_outcome": False,
            "prediction_error": 0.0,
            "mismatch": False,
            "feedback_at": "",
            "reason": "Unspecified reason",
        }
    ]
    assert report["summary"]["matched_outcome_count"] == 0


def test_feedback_outcome_calibration_orders_mismatches_by_error_then_stable_keys() -> None:
    report = build_feedback_outcome_calibration_report(
        [
            {"idea_id": "b", "predicted_recommendation": "approve", "predicted_score": 0.9, "feedback_outcome": "failed", "outcome_score": 0.1, "feedback_at": "2026-05-02", "reason": "B"},
            {"idea_id": "a", "predicted_recommendation": "approve", "predicted_score": 0.9, "feedback_outcome": "failed", "outcome_score": 0.1, "feedback_at": "2026-05-01", "reason": "A"},
            {"idea_id": "c", "predicted_recommendation": "monitor", "predicted_score": 0.55, "feedback_outcome": "failed", "outcome_score": 0.1, "feedback_at": "2026-05-01", "reason": "C"},
        ],
        mismatch_threshold=0.2,
    )

    assert [row["idea_id"] for row in report["mismatches"]] == ["a", "b", "c"]
    assert [row["prediction_error"] for row in report["mismatches"]] == [0.8, 0.8, 0.45]


def test_feedback_outcome_calibration_markdown_and_json_are_deterministic() -> None:
    report = build_feedback_outcome_calibration_report(
        [
            {"idea_id": "checkout", "predicted_recommendation": "approve", "predicted_score": 0.8, "feedback_outcome": "success", "outcome_score": 0.75},
        ]
    )

    markdown = render_feedback_outcome_calibration_markdown(report)
    assert "- Rows: 1" in markdown
    assert "- Average prediction error: 0.05" in markdown
    assert "- No feedback outcome mismatches were detected." in markdown

    rendered = render_feedback_outcome_calibration_json(report)
    assert rendered.endswith("\n")
    assert json.loads(rendered) == report
    assert rendered.splitlines()[1].startswith('  "calibration_buckets"')


def test_feedback_outcome_calibration_empty_input_is_deterministic() -> None:
    report = build_feedback_outcome_calibration_report([])

    assert report["summary"] == {
        "row_count": 0,
        "matched_outcome_count": 0,
        "mismatch_count": 0,
        "average_prediction_error": 0.0,
    }
    assert report["calibration_buckets"] == []
    assert report["mismatches"] == []
    assert "No feedback outcome rows were supplied." in render_feedback_outcome_calibration_markdown(report)
