from __future__ import annotations

import json

from max.exports import generate_signal_ingestion_lag_report
from max.exports.signal_ingestion_lag_report import render_signal_ingestion_lag_report_json, render_signal_ingestion_lag_report_markdown


def test_signal_ingestion_lag_groups_stale_sources_by_profile_and_source() -> None:
    report = generate_signal_ingestion_lag_report([{"profile": "b", "source": "crm", "last_signal_at": "2026-05-30T00:00:00Z", "expected_cadence_hours": 12, "lag_hours": 40}, {"profile": "a", "source": "web", "expected_cadence_hours": 24, "lag_hours": 26}], now="2026-05-31T12:00:00Z")

    assert [row["profile"] for row in report["rows"]] == ["b", "a"]
    assert report["rows"][0]["severity"] == "critical"
    assert report["summary"]["stale_source_count"] == 2
    assert "b / crm" in render_signal_ingestion_lag_report_markdown(report)
    json.loads(render_signal_ingestion_lag_report_json(report))
