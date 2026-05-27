from __future__ import annotations

import json

from max.exports.source_freshness_sla_report import build_source_freshness_sla_report, render_source_freshness_sla_report_json, render_source_freshness_sla_report_markdown


def test_source_freshness_sla_report_marks_breached_warning_and_healthy() -> None:
    report = build_source_freshness_sla_report([
        {"source": "missing", "max_age_minutes": 60},
        {"source": "old", "last_successful_fetch_at": "2026-05-26T22:00:00+00:00", "max_age_minutes": 60},
        {"source": "warn", "last_successful_fetch_at": "2026-05-26T23:10:00+00:00", "max_age_minutes": 60},
        {"source": "ok", "last_successful_fetch_at": "2026-05-26T23:30:00+00:00", "max_age_minutes": 60},
    ], now="2026-05-27T00:00:00+00:00")

    assert [row["breach_status"] for row in report["freshness_rows"]] == ["breached", "breached", "warning", "healthy"]
    assert report["freshness_rows"][0]["reason"] == "missing last successful fetch timestamp"
    assert report["summary"]["breached_count"] == 2
    assert json.loads(render_source_freshness_sla_report_json(report))["summary"]["warning_count"] == 1
    assert "warn warning: 50m" in render_source_freshness_sla_report_markdown(report)
