from __future__ import annotations

import json

from max.api import profile_run_cadence_drift_status_to_json


def test_profile_run_cadence_drift_status_classifies_and_sorts_profiles() -> None:
    data = json.loads(profile_run_cadence_drift_status_to_json({"schema_version": "source.v1", "metadata": {"run_id": "r1"}, "warning_drift_ratio": 1.5, "critical_drift_ratio": 2.0, "profiles": [{"profile": "Beta", "run_cadence": "daily", "expected_interval_hours": 24, "actual_interval_hours": 36, "last_run_at": "2026-06-01T00:00:00Z"}, {"profile": "Alpha", "run_cadence": "daily", "expected_interval_hours": 24, "actual_interval_hours": 60}, {"profile": "Gamma", "run_cadence": "daily", "expected_interval_hours": 24, "actual_interval_hours": 24}]}))

    assert data["schema_version"] == "max.api.profile_run_cadence_drift_status.v1"
    assert data["kind"] == "max.api.profile_run_cadence_drift_status"
    assert data["status"] == "critical"
    assert data["summary"] == {"affected_profile_count": 2, "critical_count": 1, "profile_count": 3, "status": "critical", "warning_count": 1}
    assert [row["profile"] for row in data["profiles"]] == ["alpha", "beta", "gamma"]
    assert [row["status"] for row in data["profiles"]] == ["critical", "warning", "ok"]
    assert data["metadata"]["run_id"] == "r1"
    assert data["metadata"]["source_schema_version"] == "source.v1"


def test_profile_run_cadence_drift_status_handles_malformed_numbers() -> None:
    data = json.loads(profile_run_cadence_drift_status_to_json({"items": [{"profile": "Bad", "expected_interval_hours": "oops", "actual_interval_hours": None}]}))

    assert data["status"] == "ok"
    assert data["profiles"][0]["expected_interval_hours"] == 0.0
    assert data["profiles"][0]["actual_interval_hours"] == 0.0
