from __future__ import annotations

from max.exports import generate_evaluation_score_outlier_report as exported
from max.exports.evaluation_score_outlier_report import generate_evaluation_score_outlier_report


def test_evaluation_score_outlier_report_finds_outliers_and_mismatches() -> None:
    report = generate_evaluation_score_outlier_report(
        [
            {"unit_id": "unit-a", "profile": "core", "scores": {"utility": 0.9, "risk": 0.9}, "recommendation": "reject"},
            {"unit_id": "unit-b", "profile": "core", "scores": {"utility": 0.5, "risk": 0.5}, "recommendation": "approve"},
            {"unit_id": "unit-c", "profile": "growth", "scores": {"utility": 0.1, "risk": 0.1}, "recommendation": "approve"},
        ],
        outlier_delta=0.2,
    )

    assert exported is generate_evaluation_score_outlier_report
    assert report["summary"]["mismatch_count"] == 2
    assert report["summary"]["outlier_count"] == 2
    assert report["rows"][0]["unit_id"] == "unit-a"
    assert report["rows"][0]["recommendation_mismatch"] is True

