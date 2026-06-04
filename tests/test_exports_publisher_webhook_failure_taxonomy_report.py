from __future__ import annotations

from max.exports import generate_publisher_webhook_failure_taxonomy_report


def test_retryable_failures_are_grouped() -> None:
    report = generate_publisher_webhook_failure_taxonomy_report([{"destination": "slack", "reason": "timeout", "retryable": True}])
    assert report["rows"][0]["retryable_failure_count"] == 1
    assert report["rows"][0]["status"] == "warning"


def test_terminal_failures_are_grouped() -> None:
    report = generate_publisher_webhook_failure_taxonomy_report([{"destination": "slack", "reason": "gone", "retryable": False}])
    assert report["rows"][0]["terminal_failure_count"] == 1
    assert report["rows"][0]["status"] == "critical"


def test_unknown_reasons_normalize_to_stable_bucket() -> None:
    report = generate_publisher_webhook_failure_taxonomy_report([{"destination": "slack", "retryable": True}])
    assert report["rows"][0]["failure_reason"] == "unknown"


def test_multiple_destinations_are_counted() -> None:
    report = generate_publisher_webhook_failure_taxonomy_report([{"destination": "slack", "reason": "timeout"}, {"destination": "teams", "reason": "timeout"}])
    assert report["summary"]["destination_count"] == 2


def test_empty_input_returns_empty_rows() -> None:
    report = generate_publisher_webhook_failure_taxonomy_report([])
    assert report["rows"] == []
