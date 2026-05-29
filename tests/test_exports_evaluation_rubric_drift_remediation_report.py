from __future__ import annotations

import json

from max.exports import (
    generate_evaluation_rubric_drift_remediation_report,
    render_evaluation_rubric_drift_remediation_report_markdown,
)
from max.exports.evaluation_rubric_drift_remediation_report import render_evaluation_rubric_drift_remediation_report_json


def test_grouped_drift_and_json_rendering() -> None:
    report = generate_evaluation_rubric_drift_remediation_report(
        [
            {"profile": "default", "rubric_version": "v1", "dimension": "quality", "baseline_score": 0.9, "current_score": 0.4},
            {"profile": "default", "rubric_version": "v1", "dimension": "quality", "baseline_score": 0.7, "current_score": 0.5},
        ],
        drift_threshold=0.1,
    )
    row = report["rows"][0]
    assert row["baseline_score"] == 0.8
    assert row["current_score"] == 0.45
    assert row["absolute_delta"] == 0.35
    assert row["severity"] == "critical"
    json.loads(render_evaluation_rubric_drift_remediation_report_json(report))


def test_stable_rows_empty_input_severity_ordering_and_markdown() -> None:
    report = generate_evaluation_rubric_drift_remediation_report(
        [
            {"profile": "b", "rubric_version": "v1", "dimension": "tone", "baseline_score": 0.5, "current_score": 0.5},
            {"profile": "a", "rubric_version": "v1", "dimension": "safety", "baseline_score": 0.9, "current_score": 0.6},
        ],
        drift_threshold=0.1,
    )
    assert [row["profile"] for row in report["rows"]] == ["a", "b"]
    assert report["rows"][1]["severity"] == "low"
    markdown = render_evaluation_rubric_drift_remediation_report_markdown(report)
    assert "Drifted rows: 1" in markdown
    assert "a / v1 / safety" in markdown

    empty = generate_evaluation_rubric_drift_remediation_report([])
    assert empty["summary"]["row_count"] == 0
    assert empty["rows"] == []
