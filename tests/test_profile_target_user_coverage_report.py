from __future__ import annotations

from max.exports import generate_profile_target_user_coverage_report as exported
from max.exports.profile_target_user_coverage_report import generate_profile_target_user_coverage_report


def test_profile_target_user_coverage_report_counts_missing_segments() -> None:
    report = generate_profile_target_user_coverage_report(
        [
            {"profile": "core", "target_users": ["admin", "buyer", "operator"], "covered_target_users": ["admin"]},
            {"profile": "core", "covered_segments": ["buyer"]},
            {"profile": "growth", "target_users": ["founder"], "covered_segments": ["founder"]},
        ],
        minimum_coverage_ratio=0.8,
    )

    assert exported is generate_profile_target_user_coverage_report
    assert report["summary"]["gap_count"] == 1
    assert report["rows"][0]["profile"] == "core"
    assert report["rows"][0]["missing_target_users"] == ["operator"]
    assert report["rows"][0]["coverage_ratio"] == 0.6667

