from __future__ import annotations

from max.exports import generate_embedding_reindex_queue_report as exported
from max.exports.embedding_reindex_queue_report import generate_embedding_reindex_queue_report


def test_embedding_reindex_queue_report_groups_queue_health() -> None:
    report = generate_embedding_reindex_queue_report(
        [
            {"namespace": "docs", "item_type": "signal", "age_hours": 30, "enqueued_at": "2026-06-01T00:00:00Z"},
            {"namespace": "docs", "item_type": "signal", "blocked_reason": "missing text", "enqueued_at": "2026-06-02T00:00:00Z"},
            {"namespace": "ideas", "item_type": "idea", "queued_count": 3, "priority": "normal", "enqueued_at": "2026-06-03T00:00:00Z"},
        ],
        urgent_age_hours=24,
    )

    assert exported is generate_embedding_reindex_queue_report
    assert report["summary"] == {"row_count": 2, "queued_count": 5, "blocked_count": 1, "urgent_count": 1, "urgent_age_hours": 24}
    assert report["rows"][0]["namespace"] == "docs"
    assert report["rows"][0]["status"] == "blocked"
    assert report["rows"][0]["oldest_age_hours"] == 30
    assert report["rows"][1]["queued_count"] == 3


def test_embedding_reindex_queue_report_empty_input() -> None:
    assert generate_embedding_reindex_queue_report([])["rows"] == []
