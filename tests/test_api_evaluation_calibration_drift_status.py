from __future__ import annotations

import json

from max.api.evaluation_calibration_drift_status import evaluation_calibration_drift_status_to_json


def test_evaluation_calibration_drift_status_accepts_mapping_and_classifies() -> None:
    report = json.loads(evaluation_calibration_drift_status_to_json({"min_sample_count": 10, "segments": {"core": {"sample_count": 50, "predicted_score": 0.9, "observed_success_rate": 0.6}, "growth": {"sample_count": 50, "model_score": 0.7, "observed_success_rate": 0.58}, "thin": {"sample_count": 3, "predicted_score": 1.0, "observed_success_rate": 0.0}}}))

    assert [row["segment"] for row in report["segment_rows"]] == ["core", "growth", "thin"]
    assert [row["status"] for row in report["segment_rows"]] == ["critical", "warning", "insufficient_data"]
    assert report["summary"]["worst_segment"] == "core"


def test_evaluation_calibration_drift_status_accepts_list() -> None:
    report = json.loads(evaluation_calibration_drift_status_to_json({"segments": [{"segment": "ok", "sample_count": 10, "predicted_score": 0.5, "observed_success_rate": 0.45}]}))

    assert report["segment_rows"][0]["calibration_delta"] == 0.05
    assert report["segment_rows"][0]["status"] == "ok"
