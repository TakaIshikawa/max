from __future__ import annotations

import json

from max.exports.publisher_delivery_outcome_report import (
    build_publisher_delivery_outcome_report,
    render_publisher_delivery_outcome_json,
    render_publisher_delivery_outcome_markdown,
)


def test_publisher_delivery_outcome_groups_by_target_and_outcome() -> None:
    report = build_publisher_delivery_outcome_report(
        [
            {"attempt_id": "a1", "target": "local archive", "target_type": "filesystem", "outcome": "success", "attempted_at": "2026-05-01T10:00:00Z"},
            {"attempt_id": "a2", "target": "local archive", "target_type": "filesystem", "outcome": "failed", "error": "disk full", "attempted_at": "2026-05-02T10:00:00Z"},
            {"attempt_id": "a3", "target": "tact daemon", "target_type": "tact_daemon", "outcome": "success", "attempted_at": "2026-05-03T10:00:00Z"},
        ]
    )

    assert report["summary"]["attempt_count"] == 3
    assert report["summary"]["success_count"] == 2
    assert report["summary"]["failure_count"] == 1
    assert report["outcome_counts"] == [{"outcome": "failure", "count": 1}, {"outcome": "success", "count": 2}]
    assert report["targets"][0]["target"] == "local archive"
    assert report["targets"][0]["reliability_percent"] == 50.0
    assert report["targets"][1]["reliability_percent"] == 100.0
    assert json.loads(render_publisher_delivery_outcome_json(report))["summary"]["target_count"] == 2


def test_publisher_delivery_outcome_identifies_retry_candidates_and_recent_blockers() -> None:
    report = build_publisher_delivery_outcome_report(
        [
            {
                "attempt_id": "old",
                "target": "partner portal",
                "target_type": "external_publisher",
                "status": "blocked",
                "error_message": "OAuth token expired",
                "attempted_at": "2026-05-01T09:00:00Z",
            },
            {
                "attempt_id": "new",
                "target": "tact daemon",
                "target_type": "tact",
                "outcome": "blocked",
                "error": "daemon unavailable",
                "attempted_at": "2026-05-03T09:00:00Z",
            },
            {
                "attempt_id": "manual",
                "target": "manual queue",
                "target_type": "external",
                "outcome": "failure",
                "retry_needed": False,
                "attempted_at": "2026-05-02T09:00:00Z",
            },
        ]
    )

    assert [candidate["attempt_id"] for candidate in report["retry_candidates"]] == ["old", "new"]
    assert [error["attempt_id"] for error in report["recent_blocking_errors"]] == ["new", "old"]
    assert report["summary"]["blocking_error_count"] == 2
    markdown = render_publisher_delivery_outcome_markdown(report)
    assert "tact_daemon" in markdown
    assert "- Retry candidates: 2" in markdown


def test_publisher_delivery_outcome_empty_input_is_deterministic() -> None:
    report = build_publisher_delivery_outcome_report([])

    assert report["summary"] == {
        "attempt_count": 0,
        "target_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "pending_count": 0,
        "retry_candidate_count": 0,
        "blocking_error_count": 0,
    }
    assert report["targets"] == []
    assert report["retry_candidates"] == []
    assert "No publisher delivery attempts were supplied." in render_publisher_delivery_outcome_markdown(report)
