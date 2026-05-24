from __future__ import annotations

import json

from max.exports.spec_review_rework_rate_report import (
    KIND,
    build_spec_review_rework_rate_report,
    render_spec_review_rework_rate_report_json,
)


def test_spec_review_rework_rate_summarizes_and_sorts() -> None:
    report = build_spec_review_rework_rate_report(
        [
            {"spec_id": "s1", "review_cycles": 1, "rework_events": 0},
            {"spec_id": "s2", "review_cycles": 4, "rework_events": 2, "last_reviewed_at": "2026-05-20"},
            {"spec_id": "s3", "review_cycles": 3, "rework_events": 1},
        ],
        cycle_threshold=2,
    )

    assert report["kind"] == KIND
    assert report["summary"]["total_specs"] == 3
    assert report["summary"]["specs_with_rework"] == 2
    assert report["summary"]["average_review_cycles"] == 2.67
    assert report["summary"]["highest_review_cycles"] == 4
    assert [row["spec_id"] for row in report["spec_review_rows"]] == ["s2", "s3", "s1"]
    assert json.loads(render_spec_review_rework_rate_report_json(report))["cycle_threshold"] == 2


def test_spec_review_rework_rate_defaults_missing_fields() -> None:
    report = build_spec_review_rework_rate_report([{}])

    assert report["spec_review_rows"][0]["spec_id"] == "unknown-spec-1"
    assert report["spec_review_rows"][0]["status"] == "healthy"
