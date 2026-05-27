from __future__ import annotations

import json

from max.api import pii_detection_backlog_status_to_json


def test_pii_detection_backlog_status_normalizes_counts_and_summarizes() -> None:
    parsed = json.loads(pii_detection_backlog_status_to_json({"backlog": [{"bucket": "neg", "pending_items": -1, "suspected_pii_count": -2}, {"bucket": "pii", "pending_items": 5, "suspected_pii_count": 12}, {"bucket": "old", "oldest_pending_age_hours": 80}]}))

    assert [row["bucket"] for row in parsed["buckets"]] == ["pii", "old", "neg"]
    assert parsed["buckets"][2]["pending_items"] == 0
    assert parsed["summary"]["pending_item_count"] == 5
    assert parsed["summary"]["suspected_pii_count"] == 12
    assert parsed["summary"]["critical_bucket_count"] == 1
