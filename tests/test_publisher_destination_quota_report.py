from __future__ import annotations

from max.exports import generate_publisher_destination_quota_report as exported
from max.exports.publisher_destination_quota_report import generate_publisher_destination_quota_report


def test_publisher_destination_quota_report_handles_limits_and_missing_limits() -> None:
    report = generate_publisher_destination_quota_report(
        [
            {"provider": "slack", "destination": "#launch", "attempted_count": 9, "accepted_count": 8, "quota_blocked_count": 1, "quota_limit": 10, "event_at": "2026-06-01T00:00:00Z"},
            {"provider": "teams", "destination": "ops", "status": "accepted", "event_at": "2026-06-02T00:00:00Z"},
        ],
        quota_risk_threshold=0.8,
    )

    assert exported is generate_publisher_destination_quota_report
    assert report["rows"][0]["quota_utilization"] == 0.9
    assert report["rows"][0]["status"] == "quota_risk"
    assert report["rows"][1]["quota_utilization"] is None
    assert report["rows"][1]["status"] == "ok"


def test_publisher_destination_quota_report_empty_input() -> None:
    assert generate_publisher_destination_quota_report([])["rows"] == []
