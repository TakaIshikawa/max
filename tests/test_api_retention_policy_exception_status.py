from __future__ import annotations

import json

from max.api import retention_policy_exception_status_to_json


def test_retention_policy_exception_status_flags_expired_and_missing_approval() -> None:
    parsed = json.loads(retention_policy_exception_status_to_json({"exceptions": [{"artifact_type": "log", "artifact_id": "old", "expires_at": "2026-04-01T00:00:00Z", "approved_by": "p"}, {"artifact_type": "trace", "artifact_id": "missing", "expires_at": "2026-05-30T00:00:00Z"}]}, as_of="2026-05-21T00:00:00Z"))

    assert [row["artifact_id"] for row in parsed["exceptions"]] == ["old", "missing"]
    assert parsed["exceptions"][0]["status"] == "critical"
    assert parsed["exceptions"][1]["blockers"] == ["missing_approval"]
    assert parsed["summary"]["expired_count"] == 1
    assert parsed["summary"]["missing_approval_count"] == 1
