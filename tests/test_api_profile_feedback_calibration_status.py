from __future__ import annotations

import json

from max.api.profile_feedback_calibration_status import profile_feedback_calibration_status_to_json


def test_profile_feedback_calibration_status_summarizes_profiles() -> None:
    parsed = json.loads(
        profile_feedback_calibration_status_to_json(
            {
                "min_samples": 10,
                "profiles": [
                    {"profile": "a", "sample_count": 30, "positive_count": 18, "negative_count": 12, "weight_deltas": {"fit": 0.2, "risk": -0.3}},
                    {"profile": "b", "sample_count": 4, "positive_count": 4, "negative_count": 0},
                ],
            }
        )
    )

    assert parsed["summary"]["profile_count"] == 2
    assert parsed["profiles"][0]["profile"] == "b"
    assert parsed["profiles"][1]["weight_deltas"][0] == {"dimension": "risk", "delta": -0.3}
    assert {warning["type"] for warning in parsed["warnings"]} == {"insufficient_data", "skewed_outcomes"}


def test_profile_feedback_calibration_status_aliases_zero_samples_and_metadata() -> None:
    parsed = json.loads(
        profile_feedback_calibration_status_to_json(
            {"calibrations": [{"name": "enterprise", "approved": 0, "rejected": 0, "deltas": {"cost": "bad"}}], "metadata": {"run": "r1"}},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["profiles"][0]["confidence"] == "insufficient"
    assert parsed["profiles"][0]["weight_deltas"][0]["delta"] == 0.0
    assert parsed["metadata"]["run"] == "r1"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"


def test_profile_feedback_calibration_status_confidence_thresholds() -> None:
    parsed = json.loads(profile_feedback_calibration_status_to_json({"min_samples": 10, "profiles": [{"profile": "p", "samples": 30, "approvals": 15, "rejections": 15}]}))

    assert parsed["profiles"][0]["confidence"] == "high"
    assert parsed["warnings"] == []
