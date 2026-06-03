from __future__ import annotations

import json

from max.api import spec_evidence_rehydration_queue_status_to_json


def test_spec_evidence_rehydration_queue_status_computes_age_and_attempts() -> None:
    data = json.loads(spec_evidence_rehydration_queue_status_to_json({"as_of": "2026-06-03T00:00:00Z", "warning_age_hours": 24, "critical_age_hours": 72, "max_attempts": 3, "specs": [{"spec_id": "s2", "profile": "core", "queued_at": "2026-05-30T00:00:00Z", "attempts": 1, "evidence_count": 2}, {"spec_id": "s1", "profile": "core", "queued_at": "2026-06-02T00:00:00Z", "attempts": 3, "last_error": "boom"}]}))

    assert data["status"] == "critical"
    assert data["summary"]["queued_count"] == 2
    assert data["summary"]["stuck_count"] == 2
    assert data["summary"]["retry_exhausted_count"] == 1
    assert data["summary"]["oldest_age_hours"] == 96.0
    assert data["specs"][0]["status"] == "critical"


def test_spec_evidence_rehydration_queue_status_malformed_timestamp_is_unknown() -> None:
    data = json.loads(spec_evidence_rehydration_queue_status_to_json({"items": [{"spec_id": "bad", "queued_at": "not-time"}]}))

    assert data["specs"][0]["queued_age_hours"] is None
