from __future__ import annotations

from max.exports.spec_publication_rollback_readiness_report import generate_spec_publication_rollback_readiness_report


def test_spec_publication_rollback_readiness_report_flags_missing_and_stale() -> None:
    report = generate_spec_publication_rollback_readiness_report(
        [
            {"spec_id": "s1", "destination": "slack", "rollback_plan_present": False, "last_successful_revision": "r1", "rollback_tested_at": "2026-05-01T00:00:00Z"},
            {"spec_id": "s2", "destination": "email", "rollback_plan_present": True, "last_successful_revision": "", "rollback_tested_at": "2026-05-01T00:00:00Z"},
            {"spec_id": "s3", "destination": "rss", "rollback_plan_present": True, "last_successful_revision": "r3", "rollback_tested_at": "2026-01-01T00:00:00Z"},
            {"spec_id": "s4", "destination": "webhook", "rollback_plan_present": True, "last_successful_revision": "r4", "rollback_tested_at": "2026-05-20T00:00:00Z"},
        ],
        as_of="2026-06-01T00:00:00Z",
        stale_after_days=90,
    )

    assert report["summary"] == {
        "spec_count": 4,
        "unready_spec_count": 3,
        "missing_plan_count": 2,
        "stale_test_count": 1,
    }
    assert [row["spec_id"] for row in report["spec_rows"]] == ["s1", "s2", "s3", "s4"]
    assert report["spec_rows"][0]["reason"] == "missing_rollback_plan"
    assert report["spec_rows"][2]["days_since_rollback_test"] == 151
