from __future__ import annotations

from max.exports.publisher_destination_retry_efficiency_report import generate_publisher_destination_retry_efficiency_report


def test_events_are_grouped_by_destination() -> None:
    report = generate_publisher_destination_retry_efficiency_report([{"destination": "slack", "status": "success", "attempts": 2}, {"destination": "slack", "status": "exhausted", "attempts": 4}])
    assert report["rows"][0]["destination"] == "slack"
    assert report["rows"][0]["success_count"] == 1
    assert report["rows"][0]["exhausted_retry_count"] == 1


def test_success_rate_and_average_attempts_are_zero_safe() -> None:
    report = generate_publisher_destination_retry_efficiency_report([{"destination": "email", "status": "queued"}])
    assert report["rows"][0]["retry_success_rate"] == 0.0
    assert report["rows"][0]["average_attempts_before_success"] == 0.0


def test_exhausted_retries_and_high_attempts_increase_risk() -> None:
    report = generate_publisher_destination_retry_efficiency_report([{"destination": "a", "status": "success", "attempts": 1}, {"destination": "b", "status": "success", "attempts": 5}, {"destination": "c", "status": "exhausted", "attempts": 3}])
    risks = {row["destination"]: row["efficiency_risk"] for row in report["rows"]}
    assert risks == {"a": "low", "b": "high", "c": "medium"}
