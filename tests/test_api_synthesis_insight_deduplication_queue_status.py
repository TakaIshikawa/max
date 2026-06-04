from __future__ import annotations

import json

from max.api import synthesis_insight_deduplication_queue_status_to_json


def test_empty_input_returns_stable_summary() -> None:
    report = json.loads(synthesis_insight_deduplication_queue_status_to_json({}))

    assert report["summary"] == {"blocked_queue_count": 0, "pending_count": 0, "queue_count": 0, "stale_pending_count": 0}
    assert report["queue_rows"] == []


def test_healthy_queues_sort_after_stale_work() -> None:
    report = json.loads(synthesis_insight_deduplication_queue_status_to_json({"queues": [{"profile": "growth", "batch_id": "b2", "pending_count": 3, "stale_pending_count": 0}, {"profile": "core", "batch_id": "b1", "pending_count": 2, "stale_pending_count": 2}]}))

    assert [row["status"] for row in report["queue_rows"]] == ["warning", "ok"]
    assert report["summary"]["pending_count"] == 5


def test_stale_blocked_queue_uses_critical_threshold() -> None:
    report = json.loads(synthesis_insight_deduplication_queue_status_to_json({"rows": [{"profile": "core", "batch": "nightly", "pending": 8, "stale_pending": 6}]}, stale_critical_threshold=5))

    assert report["queue_rows"][0]["status"] == "critical"
    assert report["summary"]["blocked_queue_count"] == 1


def test_malformed_counts_normalize_to_zero() -> None:
    report = json.loads(synthesis_insight_deduplication_queue_status_to_json({"items": [{"id": "bad", "pending_count": "many", "stale_pending_count": -2, "processing_count": None}]}))

    row = report["queue_rows"][0]
    assert row["pending_count"] == 0
    assert row["stale_pending_count"] == 0
    assert row["status"] == "ok"
