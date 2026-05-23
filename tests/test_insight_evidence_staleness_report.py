from __future__ import annotations

import json

from max.exports.insight_evidence_staleness_report import (
    KIND,
    build_insight_evidence_staleness_report,
    render_insight_evidence_staleness_report_json,
    render_insight_evidence_staleness_report_markdown,
)


def test_insight_evidence_staleness_report_buckets_refresh_needed() -> None:
    report = build_insight_evidence_staleness_report(
        [
            {"insight_id": "i-1", "source": "calls", "evidence_timestamp": "2026-05-10"},
            {"insight_id": "i-2", "source": "calls", "evidence_timestamp": "2026-03-01"},
            {"insight_id": "i-3", "source": "tickets"},
        ],
        as_of="2026-05-20",
        stale_after_days=30,
    )

    assert report["kind"] == KIND
    assert report["summary"]["refresh_needed_count"] == 2
    assert [row["bucket"] for row in report["freshness_buckets"]] == ["fresh", "stale", "critical", "missing"]
    assert report["refresh_needed"][0]["insight_id"] == "i-2"
    assert "Source Totals" in render_insight_evidence_staleness_report_markdown(report)
    assert json.loads(render_insight_evidence_staleness_report_json(report))["summary"]["missing_timestamp_count"] == 1


def test_insight_evidence_staleness_report_handles_empty_input() -> None:
    report = build_insight_evidence_staleness_report([])

    assert report["summary"]["evidence_count"] == 0
    assert report["source_totals"] == []
    assert "No stale insight evidence found" in render_insight_evidence_staleness_report_markdown(report)
