from __future__ import annotations

from max.exports import generate_evaluation_recommendation_distribution_report as exported
from max.exports.evaluation_recommendation_distribution_report import generate_evaluation_recommendation_distribution_report


def test_evaluation_recommendation_distribution_report_handles_empty_input() -> None:
    report = generate_evaluation_recommendation_distribution_report([])

    assert exported is generate_evaluation_recommendation_distribution_report
    assert report["summary"]["status"] == "balanced"
    assert report["summary"]["evaluation_count"] == 0
    assert report["rows"] == []


def test_evaluation_recommendation_distribution_report_counts_percentages() -> None:
    report = generate_evaluation_recommendation_distribution_report(
        [
            {"profile": "core", "model": "judge", "recommendation": "approve"},
            {"profile": "core", "model": "judge", "label": "reject"},
            {"profile": "core", "model": "judge", "outcome": "revise"},
        ]
    )

    row = report["rows"][0]
    assert row["recommendation_counts"] == {"approve": 1, "reject": 1, "revise": 1}
    assert row["recommendation_percentages"]["approve"] == 33.33
    assert row["status"] == "balanced"


def test_evaluation_recommendation_distribution_report_classifies_skew() -> None:
    report = generate_evaluation_recommendation_distribution_report(
        [{"profile": "core", "model": "judge", "recommendation": "approve"} for _ in range(4)]
        + [{"profile": "core", "model": "judge", "recommendation": "reject"}],
        skew_threshold=0.7,
        collapsed_threshold=0.9,
    )

    assert report["rows"][0]["dominant_recommendation"] == "approve"
    assert report["rows"][0]["status"] == "skewed"
