from __future__ import annotations

import json

from max.exports.idea_review_cycle_time_report import (
    build_idea_review_cycle_time_report,
    render_idea_review_cycle_time_report_json,
    render_idea_review_cycle_time_report_markdown,
)


def test_idea_review_cycle_time_report_computes_stage_metrics() -> None:
    report = build_idea_review_cycle_time_report(
        [
            {"idea_id": "i-1", "recommendation": "approve", "generated_at": "2026-05-01T00:00:00+00:00", "reviewed_at": "2026-05-01T12:00:00+00:00", "approved_at": "2026-05-02T00:00:00+00:00", "spec_generated_at": "2026-05-03T00:00:00+00:00", "published_at": "2026-05-05T00:00:00+00:00"},
            {"idea_id": "i-2", "recommendation": "reject", "generated_at": "2026-05-01T00:00:00+00:00", "reviewed_at": "2026-05-01T06:00:00+00:00", "rejected_at": "2026-05-01T08:00:00+00:00"},
        ],
        delay_threshold_hours=72,
    )

    assert report["summary"]["delayed_idea_count"] == 1
    assert report["stage_metrics"][0]["median_hours"] == 9.0
    assert report["recommendation_metrics"][0]["recommendation"] == "approve"
    assert "Stage Bottlenecks" in render_idea_review_cycle_time_report_markdown(report)
    assert json.loads(render_idea_review_cycle_time_report_json(report))["summary"]["idea_count"] == 2


def test_idea_review_cycle_time_report_handles_missing_terminal_timestamps() -> None:
    report = build_idea_review_cycle_time_report([{"idea_id": "i-1", "generated_at": "2026-05-01T00:00:00+00:00"}])

    assert report["delayed_ideas"][0]["total_cycle_hours"] is None
    assert report["stage_metrics"][0]["count"] == 0
