from __future__ import annotations

from max.exports import generate_profile_evaluation_weight_drift_report


def test_profile_evaluation_weight_drift_flags_thresholds() -> None:
    report = generate_profile_evaluation_weight_drift_report(
        [
            {"profile": "clinical", "dimension": "traceability", "baseline_weight": 1.0, "current_weight": 1.05},
            {"profile": "aero", "dimension": "safety", "baseline_weight": 1.0, "current_weight": 1.15},
            {"profile": "fin", "dimension": "risk", "baseline_weight": 1.0, "current_weight": 1.4},
        ],
        warning_delta_threshold=0.1,
        critical_delta_threshold=0.25,
    )

    assert [row["status"] for row in report["rows"]] == ["critical", "warning", "ok"]
    assert report["rows"][0]["absolute_delta"] == 0.4
    assert report["rows"][0]["percent_delta"] == 0.4


def test_profile_evaluation_weight_drift_empty() -> None:
    assert generate_profile_evaluation_weight_drift_report([])["rows"] == []
