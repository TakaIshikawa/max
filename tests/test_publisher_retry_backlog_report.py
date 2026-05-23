from __future__ import annotations

from max.exports.publisher_retry_backlog_report import (
    build_publisher_retry_backlog_report,
    render_publisher_retry_backlog_report_markdown,
)


def test_publisher_retry_backlog_report_groups_failures_and_actions() -> None:
    report = build_publisher_retry_backlog_report(
        [
            {"destination": "slack", "error_class": "rate_limit", "failed_at": "2026-05-18", "next_retry_at": "2026-05-19"},
            {"destination": "slack", "error_class": "auth", "failed_at": "2026-05-20", "next_retry_at": "2026-05-21"},
            {"destination": "email", "error_class": "timeout", "failed_at": "2026-05-10"},
        ],
        as_of="2026-05-20",
    )

    assert report["summary"]["overdue_retry_count"] == 1
    assert report["destination_totals"][1]["destination"] == "slack"
    assert [row["error_class"] for row in report["error_class_totals"]] == ["auth", "rate_limit", "timeout"]
    assert len(report["next_actions"]) == 2
    assert "Overdue Retries" in render_publisher_retry_backlog_report_markdown(report)


def test_publisher_retry_backlog_report_handles_empty_failures() -> None:
    report = build_publisher_retry_backlog_report([])

    assert report["summary"]["failure_count"] == 0
    assert report["overdue_retries"] == []
