from __future__ import annotations

import json

from max.api.publisher_retry_pressure_status import publisher_retry_pressure_status_to_json


def test_publisher_retry_pressure_status_groups_retry_jobs() -> None:
    report = json.loads(
        publisher_retry_pressure_status_to_json(
            {
                "jobs": [
                    {"target_type": "airtable", "target_name": "prod", "retry_count": 3, "next_retry_at": "2026-05-31T00:00:00Z"},
                    {"target_type": "airtable", "target_name": "prod", "retry_count": 1, "next_retry_at": "2026-05-31T03:00:00Z"},
                    {"target_type": "webhook", "target_name": "ops", "retry_count": 2},
                ]
            },
            now="2026-05-31T02:00:00Z",
            high_retry_count=3,
        )
    )

    assert report["rows"][0]["target_name"] == "prod"
    assert report["rows"][0]["total_retrying"] == 2
    assert report["rows"][0]["overdue_retry_count"] == 1
    assert report["rows"][0]["retry_count_buckets"]["3_plus"] == 1
    assert report["rows"][0]["severity"] == "critical"
