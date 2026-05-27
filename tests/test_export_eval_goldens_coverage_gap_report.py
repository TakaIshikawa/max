from __future__ import annotations

from max.exports import generate_eval_goldens_coverage_gap_report


def test_eval_goldens_coverage_gap_report_omits_healthy_by_default() -> None:
    report = generate_eval_goldens_coverage_gap_report(
        [
            {"scope": "rubric:safety", "current_count": 2, "required_count": 5},
            {"scope": "profile:enterprise", "current_count": 4, "required_count": 4},
        ]
    )

    assert report["summary"]["gap_count"] == 1
    assert report["summary"]["total_deficit"] == 3
    assert report["coverage_gaps"][0]["scope"] == "rubric:safety"
    assert report["coverage_gaps"][0]["deficit"] == 3
    assert report["coverage_gaps"][0]["severity"] == "critical"
    assert report["coverage_gaps"][0]["next_sample_target"] == 5


def test_eval_goldens_coverage_gap_report_can_include_healthy_scopes() -> None:
    report = generate_eval_goldens_coverage_gap_report(
        [{"category": "quality", "actual_count": 3, "minimum_count": 3}],
        include_healthy=True,
    )

    assert report["coverage_gaps"] == [
        {
            "scope": "quality",
            "current_count": 3,
            "required_count": 3,
            "deficit": 0,
            "severity": "healthy",
            "recommendation": "Coverage sufficient.",
            "next_sample_target": 3,
        }
    ]

