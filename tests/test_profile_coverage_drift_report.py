from __future__ import annotations

from max.exports.profile_coverage_drift_report import (
    build_profile_coverage_drift_report,
    render_profile_coverage_drift_report_markdown,
)


def test_profile_coverage_drift_report_computes_gaps_and_adjustments() -> None:
    report = build_profile_coverage_drift_report(
        [
            {"profile": "growth", "category": "activation", "source": "calls", "target_user": "admin", "expected_count": 10, "observed_count": 4, "expected_weight": 0.5, "observed_weight": 0.2},
            {"profile": "growth", "category": "retention", "source": "tickets", "target_user": "operator", "expected_count": 3, "observed_count": 3},
        ]
    )

    assert report["summary"]["severe_gap_count"] == 1
    assert report["coverage_gaps"][0]["gap"] == 6
    assert report["category_gaps"][0]["category"] == "activation"
    assert report["allocation_adjustments"][0].startswith("Allocate 6")
    assert "Suggested Allocation Adjustments" in render_profile_coverage_drift_report_markdown(report)


def test_profile_coverage_drift_report_defaults_missing_weights() -> None:
    report = build_profile_coverage_drift_report([{}])

    assert report["coverage_gaps"][0]["profile"] == "Unassigned profile"
    assert report["coverage_gaps"][0]["weight_gap"] == 0.0
