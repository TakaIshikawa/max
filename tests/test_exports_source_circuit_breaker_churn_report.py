from __future__ import annotations

import json

from max.exports.source_circuit_breaker_churn_report import build_source_circuit_breaker_churn_report, render_source_circuit_breaker_churn_report_json, render_source_circuit_breaker_churn_report_markdown


def test_source_circuit_breaker_churn_report_sorts_events_and_flags_repeated_opens() -> None:
    report = build_source_circuit_breaker_churn_report([
        {"source": "github", "adapter": "issues", "state": "closed", "timestamp": "2026-05-27T00:20:00+00:00"},
        {"source": "github", "adapter": "issues", "state": "open", "timestamp": "2026-05-27T00:00:00+00:00"},
        {"source": "github", "adapter": "issues", "state": "open", "timestamp": "2026-05-27T01:00:00+00:00"},
        {"source": "github", "adapter": "issues", "state": "closed", "timestamp": "2026-05-27T01:10:00+00:00"},
    ], repeated_open_threshold=2)

    row = report["churn_rows"][0]
    assert row["opens_per_window"] == 2
    assert row["mean_recovery_time_minutes"] == 15
    assert row["repeated_open"] is True
    assert report["summary"]["repeated_open_count"] == 1
    assert json.loads(render_source_circuit_breaker_churn_report_json(report))["summary"]["open_count"] == 2
    assert "github / issues: 2 opens" in render_source_circuit_breaker_churn_report_markdown(report)
