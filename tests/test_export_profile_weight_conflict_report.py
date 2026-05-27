from __future__ import annotations

from max.exports import generate_profile_weight_conflict_report


def test_profile_weight_conflict_report_detects_missing_and_out_of_range_weights() -> None:
    report = generate_profile_weight_conflict_report(
        [
            {"profile_id": "p1", "weights": {"quality": 0.5, "safety": -0.1}},
            {"profile_id": "p2", "weights": {"quality": 1.2}},
            {"profile_id": "p3", "weights": {"quality": 0.4, "safety": 0.6}},
        ],
        required_dimensions=["quality", "safety"],
    )

    assert report["summary"]["profiles_checked"] == 3
    assert report["summary"]["conflict_count"] == 3
    assert report["summary"]["missing_dimension_count"] == 1
    assert report["summary"]["out_of_range_count"] == 2
    assert {row["issue_type"] for row in report["conflicts"]} == {"negative_weight", "above_allowed_bounds", "missing_dimension"}

