from __future__ import annotations

import json

from max.exports.evaluation_score_drift_report import (
    KIND,
    build_evaluation_score_drift_report,
    render_evaluation_score_drift_report_json,
)


def test_evaluation_score_drift_summarizes_and_sorts() -> None:
    report = build_evaluation_score_drift_report(
        [
            {"unit_id": "u1", "dimension": "quality", "previous_score": 0.8, "current_score": 0.7},
            {"unit_id": "u2", "dimension": "risk", "previous_score": 0.2, "current_score": 0.6},
            {"unit_id": "u3", "dimension": "value", "previous_score": 0.5, "current_score": 0.52},
        ],
        drift_threshold=0.1,
    )

    assert report["kind"] == KIND
    assert report["summary"]["average_absolute_drift"] == 0.1733
    assert report["summary"]["maximum_drift"] == 0.4
    assert report["summary"]["drifted_unit_count"] == 2
    assert [row["unit_id"] for row in report["score_drift_rows"]] == ["u2", "u1", "u3"]
    assert report["score_drift_rows"][0]["direction"] == "up"
    assert json.loads(render_evaluation_score_drift_report_json(report))["summary"]["drifted_unit_count"] == 2


def test_evaluation_score_drift_defaults_missing_fields() -> None:
    report = build_evaluation_score_drift_report([{}])

    assert report["score_drift_rows"][0]["unit_id"] == "unknown-unit-1"
    assert report["score_drift_rows"][0]["status"] == "stable"
