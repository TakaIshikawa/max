from __future__ import annotations

from max.exports.feedback_reviewer_throughput_forecast_report import generate_feedback_reviewer_throughput_forecast_report


def test_feedback_reviewer_throughput_forecast_report_flags_overload_and_profiles() -> None:
    report = generate_feedback_reviewer_throughput_forecast_report(
        [
            {"reviewer": "Ada", "open_reviews": 12, "completed_last_7d": 0, "capacity_per_week": 0, "profiles": ["core"]},
            {"reviewer": "Grace", "open_reviews": 20, "completed_last_7d": 5, "capacity_per_week": 10, "profiles": ["core", "growth"]},
            {"reviewer": "Linus", "open_reviews": 2, "completed_last_7d": 7, "capacity_per_week": 7, "profiles": ["growth"]},
        ],
        warning_days_to_clear=14,
        critical_days_to_clear=30,
    )

    assert report["summary"] == {
        "reviewer_count": 3,
        "overloaded_reviewer_count": 2,
        "open_review_total": 34,
        "no_throughput_count": 1,
    }
    assert [row["reviewer"] for row in report["reviewer_rows"]] == ["Ada", "Grace", "Linus"]
    assert report["reviewer_rows"][0]["days_to_clear"] is None
    assert report["reviewer_rows"][0]["reason"] == "no_throughput"
    assert report["reviewer_rows"][1]["days_to_clear"] == 28
    assert report["profile_hot_spots"][0] == {"profile": "core", "open_review_count": 32, "reviewer_count": 2}
