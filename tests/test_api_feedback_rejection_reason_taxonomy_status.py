from __future__ import annotations

import json

from max.api import feedback_rejection_reason_taxonomy_status_to_json


def test_feedback_rejection_reason_taxonomy_status_summarizes_and_buckets_uncategorized() -> None:
    data = json.loads(feedback_rejection_reason_taxonomy_status_to_json({"reasons": [{"profile": "core", "reason": "spam", "rejection_count": 10, "mapped_category": "quality", "unmapped_count": 4, "last_seen_at": "2026-06-01"}, {"profile": "core", "reason": "dupe", "rejection_count": 10, "unmapped_count": 2}, {"profile": "growth", "reason": "ok", "rejection_count": 5, "mapped_category": "policy"}]}))
    assert data["summary"] == {"status": "critical", "reason_count": 3, "unmapped_reason_count": 2, "critical_count": 1, "warning_count": 1, "total_rejection_count": 25, "total_unmapped_count": 6}
    assert [row["reason"] for row in data["reasons"]] == ["spam", "dupe", "ok"]
    assert data["reasons"][1]["mapped_category"] == "uncategorized"
