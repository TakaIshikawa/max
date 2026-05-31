from __future__ import annotations

import json

from max.api.idea_approval_pipeline_status import idea_approval_pipeline_status_to_json


def test_idea_approval_pipeline_status_normalizes_states_and_pending_age() -> None:
    report = json.loads(
        idea_approval_pipeline_status_to_json(
            {
                "ideas": [
                    {"idea_id": "old", "state": "pending", "submitted_at": "2026-05-30T00:00:00Z"},
                    {"idea_id": "new", "state": "pending", "submitted_at": "2026-05-31T01:00:00Z"},
                    {"idea_id": "done", "state": "approved"},
                    {"idea_id": "odd", "state": "triaged"},
                ]
            },
            now="2026-05-31T02:00:00Z",
            stale_pending_seconds=3600,
            critical_pending_seconds=72000,
        )
    )

    assert report["rows"][0]["idea_id"] == "old"
    assert report["rows"][0]["severity"] == "critical"
    assert report["summary"]["state_counts"]["unknown"] == 1
    assert report["summary"]["stale_pending_count"] == 2
    assert report["summary"]["oldest_pending_age_seconds"] == 93600
