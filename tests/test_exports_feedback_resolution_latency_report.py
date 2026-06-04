from __future__ import annotations

from max.exports.feedback_resolution_latency_report import generate_feedback_resolution_latency_report


def test_groups_by_reviewer_when_present_otherwise_queue() -> None:
    report = generate_feedback_resolution_latency_report([{"reviewer_id": "r1", "queue": "triage", "created_at": "2026-06-01T00:00:00+00:00", "resolved_at": "2026-06-02T00:00:00+00:00"}, {"queue": "triage", "created_at": "2026-06-04T00:00:00+00:00"}])
    assert {row["reviewer_or_queue"] for row in report["rows"]} == {"r1", "triage"}


def test_resolved_latency_is_computed_from_created_to_resolved() -> None:
    report = generate_feedback_resolution_latency_report([{"reviewer_id": "r1", "created_at": "2026-06-01T00:00:00+00:00", "resolved_at": "2026-06-03T12:00:00+00:00"}])
    assert report["rows"][0]["average_resolved_latency_hours"] == 60.0


def test_unresolved_records_use_now_for_sla_breach_classification() -> None:
    report = generate_feedback_resolution_latency_report([{"queue": "triage", "created_at": "2026-06-01T00:00:00+00:00"}], now="2026-06-05T00:00:00+00:00")
    assert report["rows"][0]["unresolved_sla_breach_count"] == 1
    assert report["rows"][0]["latency_risk"] == "medium"
