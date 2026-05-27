from __future__ import annotations

from max.exports.evaluation_approval_gate_bottleneck_report import (
    build_evaluation_approval_gate_bottleneck_report,
    render_evaluation_approval_gate_bottleneck_report_markdown,
)


def test_evaluation_approval_gate_bottleneck_report_derives_waits_and_totals() -> None:
    report = build_evaluation_approval_gate_bottleneck_report(
        [
            {"id": "g1", "gate": "safety", "reviewer": "Mina", "profile": "prod", "submitted_at": "2026-05-25T00:00:00+00:00"},
            {"id": "g2", "gate": "quality", "reviewer": "Mina", "profile": "prod", "submitted_at": "2026-05-26T00:00:00+00:00", "reviewed_at": "2026-05-26T06:00:00+00:00"},
            {"id": "g3", "gate": "privacy", "reviewer": "Ari", "profile": "beta", "wait_hours": 10},
        ],
        threshold_hours=24,
        as_of="2026-05-27T00:00:00+00:00",
    )

    assert set(report) >= {"summary", "gates", "reviewer_totals", "profile_totals", "overdue_gates", "bottleneck_gates"}
    assert report["overdue_gates"][0]["id"] == "g1"
    assert report["bottleneck_gates"][0]["wait_hours"] == 48.0
    assert report["reviewer_totals"][0]["reviewer"] == "Mina"
    assert report["profile_totals"][0]["profile"] == "prod"


def test_evaluation_approval_gate_bottleneck_report_markdown_is_deterministic() -> None:
    report = build_evaluation_approval_gate_bottleneck_report([{"gate": "quality", "wait_hours": 2}], threshold_hours=1)

    markdown = render_evaluation_approval_gate_bottleneck_report_markdown(report)
    assert "| quality | unassigned | default | 2.0 | True |" in markdown
