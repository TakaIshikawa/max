from __future__ import annotations

import json

from max.api import evaluation_score_outlier_status_to_json


def test_evaluation_score_outlier_status_uses_explicit_z_score() -> None:
    report = json.loads(evaluation_score_outlier_status_to_json({"evaluations": [{"unit_id": "high", "profile": "ops", "score": 0.9, "median_score": 0.5, "z_score": 2.4}, {"unit_id": "normal", "score": 0.6, "median_score": 0.5, "z_score": 0.4}]}))

    assert report["outlier_evaluations"][0]["unit_id"] == "high"
    assert report["outlier_evaluations"][0]["deviation"] == 2.4
    assert report["outlier_evaluations"][0]["outlier_direction"] == "high"


def test_evaluation_score_outlier_status_falls_back_to_score_deviation() -> None:
    report = json.loads(evaluation_score_outlier_status_to_json({"z_score_threshold": 0.3, "items": [{"unit_id": "low", "score": 0.1, "median_score": 0.5}]}))

    assert report["rows"][0]["deviation"] == -0.4
    assert report["rows"][0]["outlier_direction"] == "low"
