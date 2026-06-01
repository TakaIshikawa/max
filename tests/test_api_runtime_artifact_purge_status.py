from __future__ import annotations

import json

from max.api import runtime_artifact_purge_status_to_json


def test_runtime_artifact_purge_status_groups_overdue_by_type() -> None:
    rendered = json.loads(runtime_artifact_purge_status_to_json({"as_of": "2026-06-01T00:00:00Z", "artifacts": [{"artifact_id": "b", "artifact_type": "log", "age_days": 40, "retention_days": 30, "purge_state": "pending"}, {"artifact_id": "a", "artifact_type": "bundle", "expires_at": "2026-05-01T00:00:00Z", "purge_state": "failed"}, {"artifact_id": "c", "artifact_type": "log", "age_days": 1, "retention_days": 30}]}))

    assert rendered["schema_version"] == "max.api.runtime_artifact_purge_status.v1"
    assert rendered["kind"] == "max.api.runtime_artifact_purge_status"
    assert rendered["summary"]["artifact_count"] == 3
    assert rendered["summary"]["expired_count"] == 2
    assert rendered["summary"]["purge_failed_count"] == 1
    assert rendered["summary"]["overdue_purge_count"] == 2
    assert [row["artifact_type"] for row in rendered["overdue_artifacts"]] == ["bundle", "log"]
