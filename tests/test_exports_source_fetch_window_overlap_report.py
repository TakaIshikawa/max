from __future__ import annotations

from max.exports.source_fetch_window_overlap_report import generate_source_fetch_window_overlap_report


def test_source_fetch_window_overlap_report_detects_overlaps_and_gaps() -> None:
    report = generate_source_fetch_window_overlap_report(
        [
            {"id": "w1", "source": "rss", "profile": "p", "start_at": "2026-05-31T00:00:00+00:00", "end_at": "2026-05-31T01:00:00+00:00"},
            {"id": "w2", "source": "rss", "profile": "p", "start_at": "2026-05-31T00:45:00+00:00", "end_at": "2026-05-31T02:00:00+00:00"},
            {"id": "w3", "source": "rss", "profile": "p", "start_at": "2026-05-31T03:00:00+00:00", "end_at": "2026-05-31T04:00:00+00:00"},
        ]
    )

    assert report["summary"]["total_overlap_minutes"] == 15
    assert report["summary"]["total_gap_minutes"] == 60
    assert report["issue_rows"][0]["previous_window_id"] == "w1"
    assert report["issue_rows"][0]["current_window_id"] == "w2"
    assert report["issue_rows"][0]["severity"] == "critical"
