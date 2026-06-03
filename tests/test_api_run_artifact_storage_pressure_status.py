from __future__ import annotations

import json

from max.api import run_artifact_storage_pressure_status_to_json


def test_run_artifact_storage_pressure_status_aliases_thresholds_retention_and_ordering() -> None:
    data = json.loads(run_artifact_storage_pressure_status_to_json({"items": [{"artifact_type": "logs", "bytes_used": 80, "byte_limit": 100, "retention_days": 30, "oldest_artifact_age_days": 10}, {"artifact_type": "snapshots", "bytes_used": 50, "byte_limit": 100, "retention_days": 7, "oldest_artifact_age_days": 9}, {"artifact_type": "traces", "bytes_used": 10, "byte_limit": 100}], "warning_usage_ratio": 0.5, "critical_usage_ratio": 0.85}))
    assert data["schema_version"] == "max.api.run_artifact_storage_pressure_status.v1"
    assert data["kind"] == "max.api.run_artifact_storage_pressure_status"
    assert data["status"] == "critical"
    assert data["summary"] == {"artifact_type_count": 3, "pressured_artifact_type_count": 2, "critical_count": 1, "warning_count": 1, "max_usage_ratio": 0.8}
    assert [row["artifact_type"] for row in data["artifacts"]] == ["snapshots", "logs", "traces"]
    assert data["artifacts"][0]["reason"] == "retention_age_breach"


def test_run_artifact_storage_pressure_status_zero_limit_is_deterministic() -> None:
    data = json.loads(run_artifact_storage_pressure_status_to_json({"rows": [{"artifact_type": "empty"}, {"artifact_type": "bytes", "bytes_used": 1, "byte_limit": 0}]}))
    assert data["artifacts"][0]["artifact_type"] == "bytes"
    assert data["artifacts"][0]["usage_ratio"] == 0.0
    assert data["artifacts"][0]["status"] == "critical"
    assert data["artifacts"][1]["usage_ratio"] == 0.0
