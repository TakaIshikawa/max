from __future__ import annotations

import json

from max.api.evaluation_calibration_status import evaluation_calibration_status_to_json


def test_evaluation_calibration_status_bounds_values_and_prioritizes_sample_size() -> None:
    parsed = json.loads(
        evaluation_calibration_status_to_json(
            {
                "calibrations": [
                    {"profile": "p", "dimension": "quality", "current_weight": 0.2, "recommended_weight": 0.5, "sample_size": 100, "confidence": 0.8},
                    {"profile": "p", "dimension": "freshness", "current_weight": 0.4, "recommended_weight": 0.46, "sample_size": 100, "confidence": 0.9},
                    {"profile": "q", "dimension": "risk", "current_weight": 0.4, "recommended_weight": 3, "sample_size": 2, "confidence": 1},
                    {"profile": "q", "dimension": "fit", "current_weight": -1, "recommended_weight": -1, "sample_size": 100, "confidence": 1},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["calibrations"]] == ["recalibrate", "monitor", "insufficient_data", "stable"]
    assert parsed["calibrations"][0]["delta"] == 0.3
    by_dimension = {row["dimension"]: row for row in parsed["calibrations"]}
    assert by_dimension["fit"]["current_weight"] == 0.0
    assert by_dimension["risk"]["recommended_weight"] == 1.0
    assert parsed["summary"]["insufficient_data_count"] == 1
    assert parsed["recalibration_candidates"][0]["dimension"] == "quality"


def test_evaluation_calibration_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(evaluation_calibration_status_to_json({"weights": [{"profile": "p", "dimension": "d", "current": "0.1", "recommended": "0.1", "samples": 30, "confidence": 1}]}, as_of="now"))

    assert parsed["calibrations"][0]["status"] == "stable"
    assert parsed["profile_totals"][0]["profile"] == "p"
    assert parsed["metadata"]["as_of"] == "now"
