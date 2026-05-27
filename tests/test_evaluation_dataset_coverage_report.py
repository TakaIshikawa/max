from __future__ import annotations

from max.exports.evaluation_dataset_coverage_report import build_evaluation_dataset_coverage_report, render_evaluation_dataset_coverage_report_markdown


def test_evaluation_dataset_coverage_report_clamps_and_lists_gaps() -> None:
    report = build_evaluation_dataset_coverage_report(
        [
            {"profile": "P", "source": "gold", "dimension": "safety", "expected_cases": 10, "actual_cases": 12},
            {"profile": "P", "source": "gold", "dimension": "quality", "expected_cases": 10, "actual_cases": 5},
        ]
    )

    assert report["coverage"][1]["coverage_ratio"] == 1.0
    assert report["under_covered_dimensions"][0]["dimension"] == "quality"
    assert report["summary"]["profile_count"] == 1
    assert report["summary"]["dimension_count"] == 2
    assert report["summary"]["average_coverage_ratio"] == 0.75
    assert "## Summary" in render_evaluation_dataset_coverage_report_markdown(report)
