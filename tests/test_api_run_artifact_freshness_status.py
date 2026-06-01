from __future__ import annotations

import json

from max.api import run_artifact_freshness_status_to_json


def test_run_artifact_freshness_status_flags_stale_and_missing_required() -> None:
    report = json.loads(run_artifact_freshness_status_to_json({"default_freshness_minutes": 30, "required_artifact_types": ["manifest", "report"], "artifacts": [{"run_id": "r1", "artifact_type": "manifest", "path": "/tmp/m", "age_minutes": 45}]}))

    assert report["summary"]["status"] == "critical"
    assert report["summary"]["stale_count"] == 1
    assert report["missing_required_types"] == ["report"]
    assert report["stale_artifacts"][0]["artifact_type"] == "manifest"


def test_run_artifact_freshness_status_supports_generated_at() -> None:
    report = json.loads(run_artifact_freshness_status_to_json({"as_of": "2026-06-01T01:00:00Z", "default_freshness_minutes": 120, "artifacts": [{"run_id": "r1", "artifact_type": "log", "generated_at": "2026-06-01T00:30:00Z"}]}))

    assert report["artifacts"][0]["age_minutes"] == 30.0
    assert report["summary"]["status"] == "healthy"
