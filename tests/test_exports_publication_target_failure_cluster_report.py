from __future__ import annotations

from max.exports.publication_target_failure_cluster_report import generate_publication_target_failure_cluster_report


def test_publication_target_failure_cluster_groups_failures_and_escalates() -> None:
    report = generate_publication_target_failure_cluster_report(
        [
            {"target_type": "jira", "target_name": "team", "profile": "p", "error_class": "auth", "failed_at": "2026-05-01", "message": "denied"},
            {"target_type": "jira", "target_name": "team", "profile": "p", "error_class": "auth", "failed_at": "2026-05-02"},
            {"target_type": "jira", "target_name": "team", "profile": "p", "error_class": "auth", "failed_at": "2026-05-03"},
        ],
        as_of="2026-05-31",
    )

    row = report["rows"][0]
    assert row["failure_count"] == 3
    assert row["last_failure_at"] == "2026-05-03"
    assert row["oldest_failure_age_days"] == 30
    assert row["sample_message"] == "denied"
    assert row["severity"] == "critical"
