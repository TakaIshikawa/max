from __future__ import annotations

from max.exports.insight_gap_detection_precision_report import generate_insight_gap_detection_precision_report


def test_insight_gap_detection_precision_report_computes_quality() -> None:
    report = generate_insight_gap_detection_precision_report(
        [
            {"profile": "core", "detected_gaps": 10, "validated_gaps": 4, "false_positive_gaps": 6, "window_days": 7},
            {"profile": "growth", "detected_gaps": 8, "validated_gaps": 6, "false_positive_gaps": 2, "window_days": 7},
            {"profile": "empty", "detected_gaps": 0, "validated_gaps": 0, "false_positive_gaps": 0, "window_days": 7},
        ],
        warning_precision=0.8,
        critical_precision=0.5,
    )

    assert report["summary"] == {
        "profile_count": 3,
        "low_precision_count": 2,
        "false_positive_total": 8,
        "validated_gap_total": 10,
    }
    assert report["profile_rows"][0]["profile"] == "core"
    assert report["profile_rows"][0]["precision"] == 0.4
    assert report["profile_rows"][0]["false_positive_rate"] == 0.6
    assert report["profile_rows"][0]["reason"] == "low_precision"
    assert report["profile_rows"][2]["profile"] == "empty"
    assert report["profile_rows"][2]["precision"] == 1.0
    assert report["profile_rows"][2]["reason"] == "empty_window"
