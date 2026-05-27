from __future__ import annotations

import json

from max.exports.source_duplicate_signal_report import build_source_duplicate_signal_report, render_source_duplicate_signal_report_json, render_source_duplicate_signal_report_markdown


def test_source_duplicate_signal_report_groups_duplicates_and_counts_singletons() -> None:
    report = build_source_duplicate_signal_report([
        {"source": "github", "signal_id": "sig-2", "url": "https://x"},
        {"source": "github", "signal_id": "sig-1", "url": "https://x"},
        {"source": "github", "signal_id": "sig-3", "url": "https://y"},
    ])

    assert report["summary"]["signal_count"] == 3
    assert report["summary"]["singleton_count"] == 1
    assert report["duplicate_rows"][0]["canonical_signal_id"] == "sig-1"
    assert report["duplicate_rows"][0]["affected_signal_ids"] == ["sig-1", "sig-2"]
    assert json.loads(render_source_duplicate_signal_report_json(report))["summary"]["duplicate_group_count"] == 1
    assert "github https://x: 2 signals" in render_source_duplicate_signal_report_markdown(report)
