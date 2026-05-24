from __future__ import annotations

from max.exports.publisher_webhook_delivery_report import generate_publisher_webhook_delivery_report


def test_publisher_webhook_delivery_report_groups_destinations_and_status_families() -> None:
    report = generate_publisher_webhook_delivery_report(
        {
            "as_of": "2026-05-24T12:00:00Z",
            "success_rate_threshold": 0.75,
            "attempts": [
                {
                    "id": "1",
                    "payload_id": "p1",
                    "destination": "crm",
                    "status_code": 200,
                    "attempted_at": "2026-05-24T10:00:00Z",
                },
                {
                    "id": "2",
                    "payload_id": "p2",
                    "destination": "crm",
                    "status_code": 500,
                    "attempted_at": "2026-05-24T09:00:00Z",
                    "retries": 2,
                    "error": "server error",
                },
                {
                    "id": "3",
                    "payload_id": "p3",
                    "destination": "billing",
                    "status_code": 429,
                    "attempted_at": "2026-05-23T12:00:00Z",
                    "retry_count": 1,
                    "error": "rate limited",
                },
                {
                    "id": "4",
                    "payload_id": "p4",
                    "destination": "billing",
                    "status_code": 204,
                    "attempted_at": "2026-05-24T11:00:00Z",
                },
            ],
        }
    )

    assert report["summary"]["attempt_count"] == 4
    assert report["summary"]["retry_count"] == 3
    assert [(row["status_family"], row["count"]) for row in report["status_family_counts"]] == [
        ("2xx", 2),
        ("4xx", 1),
        ("5xx", 1),
    ]
    assert [row["destination"] for row in report["destinations"]] == ["billing", "crm"]
    assert report["destinations"][0]["success_rate"] == 0.5
    assert report["destinations"][0]["oldest_undelivered_age_hours"] == 24
    assert report["destinations"][0]["last_error"] == "rate limited"
    assert [row["destination"] for row in report["flagged_destinations"]] == ["billing", "crm"]


def test_publisher_webhook_delivery_report_empty_input() -> None:
    report = generate_publisher_webhook_delivery_report({"attempts": []})

    assert report["summary"]["attempt_count"] == 0
    assert report["destinations"] == []
    assert report["undelivered_backlog"] == []
