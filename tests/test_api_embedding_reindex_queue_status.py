from __future__ import annotations

import json

from max.api import embedding_reindex_queue_status_to_json


def test_embedding_reindex_queue_status_derives_age_and_priority_order() -> None:
    parsed = json.loads(embedding_reindex_queue_status_to_json({"queue": [{"id": "old", "type": "signals", "enqueued_at": "2026-05-26T00:00:00Z"}, {"id": "blocked", "item_type": "ideas", "submitted_at": "2026-05-26T20:00:00Z", "blocked_reason": "missing text"}, {"id": "urgent", "item_type": "insights", "submitted_at": "2026-05-26T22:00:00Z", "priority": "urgent"}]}, as_of="2026-05-27T00:00:00Z"))

    assert parsed["schema_version"] == "max.api.embedding_reindex_queue_status.v1"
    assert [row["item_id"] for row in parsed["jobs"]] == ["blocked", "urgent", "old"]
    assert parsed["summary"]["queued_count"] == 3
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["summary"]["urgent_count"] == 2
    assert parsed["summary"]["oldest_age_hours"] == 24
