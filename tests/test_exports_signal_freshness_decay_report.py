from __future__ import annotations

import json

from max.exports.signal_freshness_decay_report import generate_signal_freshness_decay_report, render_signal_freshness_decay_report_json, render_signal_freshness_decay_report_markdown


def test_empty_input_has_zero_counts_and_low_risk() -> None:
    report = generate_signal_freshness_decay_report([], now="2026-06-05T00:00:00+00:00")
    assert report["summary"] == {"source_count": 0, "signal_count": 0, "stale_signal_count": 0, "malformed_timestamp_count": 0, "freshness_risk": "low"}
    assert report["rows"] == []


def test_mixed_freshness_buckets_are_grouped_by_source() -> None:
    report = generate_signal_freshness_decay_report(
        [
            {"source": "github", "seen_at": "2026-06-04T12:00:00+00:00"},
            {"source": "github", "seen_at": "2026-06-01T00:00:00+00:00"},
            {"source": "github", "seen_at": "2026-05-20T00:00:00+00:00"},
        ],
        now="2026-06-05T00:00:00+00:00",
    )
    row = report["rows"][0]
    assert (row["fresh_count"], row["aging_count"], row["stale_count"]) == (1, 1, 1)
    assert row["oldest_seen_at"] == "2026-05-20T00:00:00+00:00"
    assert row["freshness_risk"] == "medium"


def test_malformed_timestamps_are_counted_without_crashing() -> None:
    report = generate_signal_freshness_decay_report([{"source": "rss", "seen_at": "bad"}, {"source": "rss"}], now="2026-06-05T00:00:00+00:00")
    assert report["rows"][0]["malformed_timestamp_count"] == 2
    assert report["rows"][0]["stale_ratio"] == 1.0
    assert report["summary"]["malformed_timestamp_count"] == 2


def test_rows_sort_by_highest_stale_ratio_then_source() -> None:
    report = generate_signal_freshness_decay_report(
        [
            {"source": "zeta", "seen_at": "2026-05-01T00:00:00+00:00"},
            {"source": "alpha", "seen_at": "2026-05-01T00:00:00+00:00"},
            {"source": "mid", "seen_at": "2026-06-04T00:00:00+00:00"},
        ],
        now="2026-06-05T00:00:00+00:00",
    )
    assert [row["source"] for row in report["rows"]] == ["alpha", "zeta", "mid"]


def test_render_helpers_are_deterministic() -> None:
    report = generate_signal_freshness_decay_report([{"source": "github", "seen_at": "2026-06-04T00:00:00+00:00"}])
    assert json.loads(render_signal_freshness_decay_report_json(report)) == report
    assert "github" in render_signal_freshness_decay_report_markdown(report)
