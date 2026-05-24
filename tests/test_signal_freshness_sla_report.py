from __future__ import annotations

import json

from max.exports.signal_freshness_sla_report import (
    KIND,
    build_signal_freshness_sla_report,
    render_signal_freshness_sla_report_json,
    render_signal_freshness_sla_report_markdown,
)


def test_signal_freshness_sla_report_computes_stale_sources() -> None:
    report = build_signal_freshness_sla_report(
        [
            {"source": "rss", "age_hours": 40, "max_age_hours": 24, "signal_count": 5, "severity": "high"},
            {
                "source": "github",
                "latest_signal_at": "2026-05-20T00:00:00+00:00",
                "fetched_at": "2026-05-20T05:00:00+00:00",
                "max_age_hours": 4,
                "signal_count": 2,
                "severity": "critical",
            },
            {"source": "slack", "age_hours": 1, "max_age_hours": 24, "signal_count": 10},
        ]
    )

    assert report == build_signal_freshness_sla_report(
        [
            {"source": "rss", "age_hours": 40, "max_age_hours": 24, "signal_count": 5, "severity": "high"},
            {
                "source": "github",
                "latest_signal_at": "2026-05-20T00:00:00+00:00",
                "fetched_at": "2026-05-20T05:00:00+00:00",
                "max_age_hours": 4,
                "signal_count": 2,
                "severity": "critical",
            },
            {"source": "slack", "age_hours": 1, "max_age_hours": 24, "signal_count": 10},
        ]
    )
    assert report["kind"] == KIND
    assert report["summary"]["stale_source_count"] == 2
    assert report["summary"]["maximum_breach_hours"] == 16.0
    assert [row["source"] for row in report["stale_sources"]] == ["rss", "github"]
    assert report["source_freshness"][0]["age_hours"] == 5.0
    assert report["source_freshness"][0]["newest_signal_at"] == "2026-05-20T00:00:00+00:00"
    assert report["source_freshness"][0]["sla_hours"] == 4.0
    assert report["source_freshness"][0]["breach_hours"] == 1.0
    assert report["source_freshness"][0]["status"] == "stale"
    assert json.loads(render_signal_freshness_sla_report_json(report))["summary"]["sla_breach_count"] == 2
    assert "- Stale sources: 2" in render_signal_freshness_sla_report_markdown(report)


def test_signal_freshness_sla_report_defaults_missing_fields() -> None:
    report = build_signal_freshness_sla_report([{}])

    assert report["source_freshness"][0]["source"] == "Unknown source"
    assert report["source_freshness"][0]["age_hours"] == 0.0
    assert report["stale_sources"] == []
    assert report["remediation_actions"] == []
    assert "No stale sources detected." in render_signal_freshness_sla_report_markdown(report)


def test_signal_freshness_sla_report_empty_input() -> None:
    report = build_signal_freshness_sla_report([])

    assert report["summary"]["total_source_count"] == 0
    assert report["summary"]["stale_source_count"] == 0
    assert report["summary"]["maximum_breach_hours"] == 0.0
    assert report["source_freshness"] == []
