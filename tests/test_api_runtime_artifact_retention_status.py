from __future__ import annotations

import json

from max.api import runtime_artifact_retention_status_to_json


def test_runtime_artifact_retention_status_zero_artifacts() -> None:
    report = json.loads(runtime_artifact_retention_status_to_json({}))
    assert report["summary"]["health"] == "healthy"
    assert report["summary"]["breach_rate"] == 0.0


def test_runtime_artifact_retention_status_groups_artifact_types() -> None:
    report = json.loads(runtime_artifact_retention_status_to_json({"artifacts": [{"artifact_type": "log", "status": "retained"}, {"artifact_type": "log", "status": "expired"}, {"artifact_type": "trace", "status": "missing"}]}))
    assert report["summary"]["expired_count"] == 1
    assert report["artifact_types"][0]["artifact_type"] in {"log", "trace"}


def test_runtime_artifact_retention_status_critical_threshold() -> None:
    report = json.loads(runtime_artifact_retention_status_to_json({"critical_breach_rate": 0.5, "artifacts": [{"artifact_type": "trace", "status": "missing"}, {"artifact_type": "trace", "status": "oversized"}]}))
    assert report["summary"]["health"] == "critical"
    assert report["summary"]["highest_risk_artifact_type"] == "trace"

