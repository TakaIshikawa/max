from __future__ import annotations

import json

from max.exports.insight_attribution_completeness_report import (
    KIND,
    build_insight_attribution_completeness_report,
    render_insight_attribution_completeness_report_json,
)


def test_insight_attribution_completeness_classifies_rows() -> None:
    report = build_insight_attribution_completeness_report(
        [
            {"insight_id": "i1", "evidence_signal_ids": ["s1", "s2"], "evidence_sources": ["rss", "github"]},
            {"insight_id": "i2", "evidence_signal_ids": ["s3"], "evidence_sources": ["rss"]},
        ]
    )

    assert report["kind"] == KIND
    assert report["summary"]["total_insights"] == 2
    assert report["summary"]["incomplete_insights"] == 1
    assert report["summary"]["average_evidence_count"] == 1.5
    assert report["summary"]["lowest_source_diversity"] == 1
    assert report["incomplete_attribution"][0]["missing_evidence_count"] == 1
    assert report["incomplete_attribution"][0]["missing_source_count"] == 1
    assert json.loads(render_insight_attribution_completeness_report_json(report))["summary"]["total_insights"] == 2


def test_insight_attribution_completeness_defaults_missing_fields() -> None:
    report = build_insight_attribution_completeness_report([{}])

    row = report["insight_attribution"][0]
    assert row["insight_id"] == "unknown-insight-1"
    assert row["status"] == "incomplete"
