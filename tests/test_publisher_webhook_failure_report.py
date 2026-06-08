from __future__ import annotations

from max.exports import generate_publisher_webhook_failure_report as exported
from max.exports.publisher_webhook_failure_report import generate_publisher_webhook_failure_report


def test_publisher_webhook_failure_report_marks_healthy_destination() -> None:
    report = generate_publisher_webhook_failure_report(
        [
            {"destination": "slack", "event_type": "idea.created", "status_code": 200, "status": "delivered"},
            {"destination": "slack", "event_type": "idea.created", "status_code": 204, "status": "delivered"},
        ]
    )

    assert exported is generate_publisher_webhook_failure_report
    assert report["summary"]["healthy_count"] == 1
    assert report["summary"]["failure_count"] == 0
    assert report["rows"][0]["status"] == "healthy"
    assert report["rows"][0]["status_code_families"]["2xx"] == 2


def test_publisher_webhook_failure_report_marks_degraded_destination_with_4xx_failure() -> None:
    report = generate_publisher_webhook_failure_report(
        [
            {"destination": "teams", "event": "spec.published", "http_status": 200},
            {"destination": "teams", "event": "spec.published", "http_status": 200},
            {"destination": "teams", "event": "spec.published", "http_status": 200},
            {"destination": "teams", "event": "spec.published", "http_status": 404},
        ],
        degraded_failure_rate_threshold=0.20,
        failing_failure_rate_threshold=0.50,
    )

    row = report["rows"][0]
    assert row["destination"] == "teams"
    assert row["event_type"] == "spec.published"
    assert row["status"] == "degraded"
    assert row["failure_rate"] == 0.25
    assert row["4xx_count"] == 1
    assert report["summary"]["degraded_count"] == 1


def test_publisher_webhook_failure_report_marks_failing_and_counts_failure_kinds() -> None:
    report = generate_publisher_webhook_failure_report(
        [
            {"destination_id": "webhook-a", "type": "feedback.received", "response_code": 500},
            {"destination_id": "webhook-a", "type": "feedback.received", "status": "timeout"},
            {"destination_id": "webhook-a", "type": "feedback.received", "status": "retry_exhausted"},
            {"destination_id": "webhook-a", "type": "feedback.received", "response_code": 202},
        ],
        degraded_failure_rate_threshold=0.25,
        failing_failure_rate_threshold=0.75,
    )

    row = report["rows"][0]
    assert row["status"] == "failing"
    assert row["attempt_count"] == 4
    assert row["failure_count"] == 3
    assert row["5xx_count"] == 1
    assert row["timeout_count"] == 1
    assert row["retry_exhausted_count"] == 1
    assert report["summary"]["failing_count"] == 1
    assert report["summary"]["5xx_count"] == 1
    assert report["summary"]["timeout_count"] == 1
    assert report["summary"]["retry_exhausted_count"] == 1
