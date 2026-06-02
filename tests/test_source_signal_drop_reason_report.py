from __future__ import annotations

import json

from max.exports.source_signal_drop_reason_report import build_source_signal_drop_reason_report, render_source_signal_drop_reason_report_json, render_source_signal_drop_reason_report_markdown


def test_source_signal_drop_reason_report_groups_and_sorts() -> None:
    report = build_source_signal_drop_reason_report([
        {"source": "github", "signal_id": "2", "status": "dropped", "drop_reason": "duplicate", "profile": "dev"},
        {"source": "github", "signal_id": "1", "status": "dropped"},
        {"source": "hn", "signal_id": "3", "status": "accepted"},
    ])

    assert report["schema_version"] == "max.source_signal_drop_reason_report.v1"
    assert report["kind"] == "max.source_signal_drop_reason_report"
    assert report["summary"] == {"dropped_count": 2, "accepted_count": 1, "unknown_reason_count": 1}
    assert [row["signal_id"] for row in report["dropped_signals"]] == ["2", "1"]
    assert "github / duplicate / 2" in render_source_signal_drop_reason_report_markdown(report)
    assert json.loads(render_source_signal_drop_reason_report_json(report))["summary"]["dropped_count"] == 2
