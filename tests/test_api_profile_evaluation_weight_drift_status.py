from __future__ import annotations

import json

from max.api import profile_evaluation_weight_drift_status_to_json


def test_profile_evaluation_weight_drift_reports_dimension_and_profile_severity() -> None:
    report = json.loads(profile_evaluation_weight_drift_status_to_json({"profiles": [{"profile": "default", "baseline_weights": {"quality": 0.5, "safety": 0.5}, "active_weights": {"quality": 0.8, "safety": 0.4, "tone": 0.1}}]}))

    assert report["summary"]["severity"] == "critical"
    profile = report["profiles"][0]
    assert profile["severity"] == "critical"
    assert profile["dimensions"][0]["absolute_drift"] == 0.3
    assert [row for row in profile["dimensions"] if row["dimension"] == "tone"][0]["missing_baseline"] is True


def test_profile_evaluation_weight_drift_empty_is_ok() -> None:
    report = json.loads(profile_evaluation_weight_drift_status_to_json({}))

    assert report["summary"]["severity"] == "ok"
