from __future__ import annotations

import json

from max.api import profile_run_parameter_drift_status_to_json


def test_profile_run_parameter_drift_status_detects_material_changes() -> None:
    data = json.loads(profile_run_parameter_drift_status_to_json({"profile_runs": [{"profile_id": "p1", "baseline": {"source_weights": {"a": 1}, "budget_caps": {"tokens": 10}}, "current": {"source_weights": {"a": 2}, "budget_caps": {"tokens": 10}}}, {"profile_id": "p2", "baseline": {"enabled_stages": ["a"]}, "current": {"enabled_stages": ["b"]}}]}))

    assert data["summary"]["drifted_profile_count"] == 2
    assert data["summary"]["material_change_count"] == 2
    assert data["rows"][0]["severity"] == "critical"


def test_profile_run_parameter_drift_status_accepts_items_and_parameters_alias() -> None:
    data = json.loads(profile_run_parameter_drift_status_to_json({"items": [{"id": "p", "baseline": {"evaluation_weights": {"q": 1}}, "parameters": {"evaluation_weights": {"q": 1}}}]}))

    assert data["summary"]["status"] == "ok"
    assert data["rows"][0]["changed_fields"] == []
