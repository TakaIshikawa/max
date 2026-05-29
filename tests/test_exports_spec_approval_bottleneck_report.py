from __future__ import annotations

from max.exports import generate_spec_approval_bottleneck_report, render_spec_approval_bottleneck_report_markdown


def test_spec_approval_bottleneck_counts_statuses_and_overdue() -> None:
    report = generate_spec_approval_bottleneck_report(
        [
            {"reviewer": "alex", "spec_type": "launch", "approval_stage": "security", "status": "pending", "wait_hours": 72},
            {"reviewer": "alex", "spec_type": "launch", "approval_stage": "security", "status": "approved", "wait_hours": 4},
            {"reviewer": "alex", "spec_type": "launch", "approval_stage": "security", "status": "rejected", "wait_hours": 8},
        ],
        sla_hours=48,
    )
    row = report["rows"][0]
    assert row["pending_count"] == 1
    assert row["approved_count"] == 1
    assert row["rejected_count"] == 1
    assert row["median_wait_hours"] == 8.0
    assert row["overdue_count"] == 1
    assert "alex / launch / security" in render_spec_approval_bottleneck_report_markdown(report)
