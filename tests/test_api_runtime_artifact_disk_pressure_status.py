from __future__ import annotations

import json

from max.api import runtime_artifact_disk_pressure_status_to_json


def test_runtime_artifact_disk_pressure_status_reports_worst_type_and_critical() -> None:
    data = json.loads(runtime_artifact_disk_pressure_status_to_json({"warning_bytes": 100, "critical_bytes": 200, "artifacts": [{"artifact_id": "a1", "artifact_type": "logs", "bytes": 80}, {"artifact_id": "a2", "artifact_type": "snapshots", "size_bytes": 150}]}))

    assert data["status"] == "critical"
    assert data["artifact_count"] == 2
    assert data["total_bytes"] == 230
    assert data["max_bytes"] == 200
    assert data["worst_artifact_type"] == "snapshots"
    assert data["worst_artifact_type_bytes"] == 150


def test_runtime_artifact_disk_pressure_status_supports_warning_and_empty() -> None:
    warning = json.loads(runtime_artifact_disk_pressure_status_to_json({"warning_bytes": 100, "critical_bytes": 200, "items": [{"type": "logs", "bytes": 120}]}))
    empty = json.loads(runtime_artifact_disk_pressure_status_to_json({}))

    assert warning["status"] == "warning"
    assert empty["status"] == "ok"
    assert empty["worst_artifact_type"] is None
