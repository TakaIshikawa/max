from __future__ import annotations

import json

from max.api import retrospective_learning_health_status_to_json


def test_retrospective_learning_health_status_reports_pending_outcomes() -> None:
    data = json.loads(retrospective_learning_health_status_to_json({"now": "2026-05-31T00:00:00Z", "feedback_outcomes": [{"id": "old", "outcome_at": "2026-05-26T00:00:00Z"}, {"id": "done", "outcome_at": "2026-05-30T00:00:00Z", "processed": True}], "learning_job": {"latest_applied_outcome_at": "2026-05-25T00:00:00Z"}}))

    assert data["summary"]["unprocessed_outcome_count"] == 1
    assert data["summary"]["oldest_pending_age_hours"] == 120
    assert data["summary"]["status"] == "warning"


def test_retrospective_learning_health_status_includes_latest_checkpoint() -> None:
    data = json.loads(retrospective_learning_health_status_to_json({"now": "2026-05-31T00:00:00Z", "checkpoint": {"latest_applied_outcome_at": "2026-05-30T00:00:00Z"}}))

    assert data["summary"]["latest_applied_outcome_at"] == "2026-05-30T00:00:00Z"
