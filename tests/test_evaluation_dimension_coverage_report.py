from __future__ import annotations

from max.exports import generate_evaluation_dimension_coverage_report as exported
from max.exports.evaluation_dimension_coverage_report import generate_evaluation_dimension_coverage_report


def test_evaluation_dimension_coverage_report_handles_empty_input() -> None:
    report = generate_evaluation_dimension_coverage_report([])

    assert exported is generate_evaluation_dimension_coverage_report
    assert report["summary"]["status"] == "complete"
    assert len(report["summary"]["expected_dimensions"]) == 7
    assert report["rows"] == []


def test_evaluation_dimension_coverage_report_computes_missing_dimensions() -> None:
    report = generate_evaluation_dimension_coverage_report(
        [{"profile": "core", "rubric_version": "v2", "scores": {"accuracy": 1, "risk": 1}}],
        expected_dimensions=["accuracy", "risk", "clarity"],
    )

    row = report["rows"][0]
    assert row["coverage_percent"] == 66.67
    assert row["missing_dimensions"] == ["clarity"]
    assert row["partial_evaluation_count"] == 1
    assert row["status"] == "sparse"


def test_evaluation_dimension_coverage_report_classifies_complete() -> None:
    report = generate_evaluation_dimension_coverage_report(
        [{"profile": "core", "version": "v2", "dimensions": ["accuracy", "risk"]}],
        expected_dimensions=["accuracy", "risk"],
    )

    assert report["rows"][0]["status"] == "complete"
