from __future__ import annotations

from max.exports.feedback_outcome_latency_by_profile_report import generate_feedback_outcome_latency_by_profile_report


def test_feedback_outcome_latency_report_empty_input() -> None:
    report = generate_feedback_outcome_latency_by_profile_report([])

    assert report["summary"] == {"profile_count": 0, "valid_record_count": 0, "invalid_record_count": 0, "overdue_count": 0}
    assert report["profiles"] == []


def test_feedback_outcome_latency_report_groups_and_sorts_by_latency() -> None:
    report = generate_feedback_outcome_latency_by_profile_report(
        [
            {"id": "a", "profile": "enterprise", "idea_created_at": "2026-05-01T00:00:00Z", "outcome_recorded_at": "2026-05-05T00:00:00Z"},
            {"id": "b", "profile": "startup", "idea_created_at": "2026-05-01T00:00:00Z", "outcome_recorded_at": "2026-05-02T00:00:00Z"},
            {"id": "c", "profile": "enterprise", "idea_created_at": "2026-05-01T00:00:00Z", "outcome_recorded_at": "2026-05-03T00:00:00Z"},
        ],
        now="2026-06-01T00:00:00Z",
    )

    assert [row["profile"] for row in report["profiles"]] == ["enterprise", "startup"]
    assert report["profiles"][0]["count"] == 2
    assert report["profiles"][0]["average_latency_hours"] == 72.0
    assert report["profiles"][0]["p95_latency_hours"] == 96.0


def test_feedback_outcome_latency_report_classifies_overdue_separately() -> None:
    report = generate_feedback_outcome_latency_by_profile_report(
        [{"profile": "enterprise", "idea_created_at": "2026-05-01T00:00:00Z", "outcome_recorded_at": "2026-05-04T01:00:00Z"}],
        sla_hours=72,
    )

    assert report["summary"]["overdue_count"] == 1
    assert report["profiles"][0]["overdue_count"] == 1
    assert report["summary"]["invalid_record_count"] == 0


def test_feedback_outcome_latency_report_tracks_missing_timestamps_as_invalid() -> None:
    report = generate_feedback_outcome_latency_by_profile_report(
        [
            {"id": "missing-created", "profile": "startup", "outcome_recorded_at": "2026-05-04T01:00:00Z"},
            {"id": "missing-outcome", "profile": "enterprise", "idea_created_at": "2026-05-01T00:00:00Z"},
        ]
    )

    assert report["summary"]["invalid_record_count"] == 2
    assert [row["id"] for row in report["invalid_records"]] == ["missing-outcome", "missing-created"]
