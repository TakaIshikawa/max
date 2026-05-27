from __future__ import annotations

import json

from max.exports.source_backfill_gap_report import build_source_backfill_gap_report, render_source_backfill_gap_report_json, render_source_backfill_gap_report_markdown


def test_source_backfill_gap_report_detects_and_prioritizes_missing_intervals() -> None:
    report = build_source_backfill_gap_report([
        {"source": "github", "importance": "critical", "expected_start": "2026-05-01T00:00:00+00:00", "expected_end": "2026-05-02T00:00:00+00:00", "observed_windows": [{"start": "2026-05-01T00:00:00+00:00", "end": "2026-05-01T06:00:00+00:00"}, {"start": "2026-05-01T12:00:00+00:00", "end": "2026-05-02T00:00:00+00:00"}]}
    ])

    assert report["summary"]["gap_count"] == 1
    assert report["gap_rows"][0]["missing_interval"] == "2026-05-01T06:00:00+00:00/2026-05-01T12:00:00+00:00"
    assert report["gap_rows"][0]["gap_duration_hours"] == 6
    assert report["gap_rows"][0]["priority"] == "high"
    assert json.loads(render_source_backfill_gap_report_json(report))["summary"]["source_count"] == 1
    assert "github 2026-05-01T06:00:00+00:00" in render_source_backfill_gap_report_markdown(report)
