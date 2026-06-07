from __future__ import annotations

from max.exports import generate_feedback_loop_weight_impact_report


def test_feedback_loop_weight_impact_groups_by_profile_and_dimension() -> None:
    report = generate_feedback_loop_weight_impact_report(
        [
            {"profile": "clinical", "dimension": "traceability", "outcome": "approved", "starting_weight": 1.0, "ending_weight": 1.1},
            {"profile": "clinical", "dimension": "traceability", "outcome": "rejected", "ending_weight": 1.25},
            {"profile": "aero", "dimension": "safety", "approval_count": 2, "rejection_count": 0, "starting_weight": 2.0, "ending_weight": 2.05},
        ],
        material_delta_threshold=0.2,
    )

    assert report["summary"]["row_count"] == 2
    assert report["rows"][0]["profile"] == "clinical"
    assert report["rows"][0]["approval_count"] == 1
    assert report["rows"][0]["rejection_count"] == 1
    assert report["rows"][0]["weight_delta"] == 0.25
    assert report["rows"][0]["status"] == "material"
    assert report["rows"][1]["status"] == "stable"


def test_feedback_loop_weight_impact_empty_is_ok() -> None:
    assert generate_feedback_loop_weight_impact_report([])["rows"] == []
