from __future__ import annotations

import json

from max.exports.signal_source_quota_burn_report import build_signal_source_quota_burn_report, render_signal_source_quota_burn_report_json, render_signal_source_quota_burn_report_markdown


def test_signal_source_quota_burn_computes_remaining_and_risk() -> None:
    report = build_signal_source_quota_burn_report([
        {"source": "github", "quota_limit": 100, "consumed_count": 99, "burn_rate": 12, "reset_at": "2026-06-02T00:00:00Z"},
        {"source": "hn", "quota_limit": 100, "consumed_count": 50},
    ])

    assert report["source_rows"][0]["source"] == "github"
    assert report["source_rows"][0]["remaining_count"] == 1
    assert report["source_rows"][0]["utilization_percent"] == 99.0
    assert report["source_rows"][0]["exhaustion_risk"] == "critical"
    assert "github: 99.0% used" in render_signal_source_quota_burn_report_markdown(report)
    assert json.loads(render_signal_source_quota_burn_report_json(report))["summary"]["critical_count"] == 1
