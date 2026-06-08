from __future__ import annotations

from max.exports import generate_source_adapter_backfill_completeness_report as exported
from max.exports.source_adapter_backfill_completeness_report import generate_source_adapter_backfill_completeness_report


def test_backfill_completeness_report_marks_complete_windows() -> None:
    report = generate_source_adapter_backfill_completeness_report(
        [{"id": "w1", "adapter": "rss", "profile": "growth", "start_at": "2026-06-01T00:00:00Z", "end_at": "2026-06-01T02:00:00Z"}],
        [{"adapter": "rss", "profile": "growth", "start_at": "2026-06-01T00:00:00Z", "end_at": "2026-06-01T02:00:00Z"}],
    )

    assert exported is generate_source_adapter_backfill_completeness_report
    assert report["summary"]["completeness"] == 1.0
    assert report["summary"]["complete_count"] == 1
    assert report["rows"][0]["status"] == "complete"
    assert report["rows"][0]["covered_minutes"] == 120
    assert report["rows"][0]["missing_intervals"] == []


def test_backfill_completeness_report_identifies_gaps_and_partial_windows() -> None:
    report = generate_source_adapter_backfill_completeness_report(
        [
            {"id": "w1", "adapter": "rss", "profile": "growth", "start_at": "2026-06-01T00:00:00Z", "end_at": "2026-06-01T04:00:00Z"},
            {"id": "w2", "adapter": "rss", "profile": "growth", "start_at": "2026-06-02T00:00:00Z", "end_at": "2026-06-02T01:00:00Z"},
        ],
        [
            {"adapter": "rss", "profile": "growth", "start_at": "2026-06-01T00:00:00Z", "end_at": "2026-06-01T01:00:00Z"},
            {"adapter": "rss", "profile": "growth", "start_at": "2026-06-01T02:00:00Z", "end_at": "2026-06-01T04:00:00Z"},
        ],
    )

    rows = {row["window_id"]: row for row in report["rows"]}
    assert rows["w1"]["status"] == "partial"
    assert rows["w1"]["completeness"] == 0.75
    assert rows["w1"]["missing_intervals"] == [{"start_at": "2026-06-01T01:00:00Z", "end_at": "2026-06-01T02:00:00Z", "minutes": 60}]
    assert rows["w2"]["status"] == "missing"
    assert report["summary"]["partial_count"] == 1
    assert report["summary"]["missing_count"] == 1
