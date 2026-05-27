from __future__ import annotations

import json

from max.api.publisher_destination_health_status import publisher_destination_health_status_to_json


def test_publisher_destination_health_status_marks_degraded_and_unavailable() -> None:
    report = json.loads(
        publisher_destination_health_status_to_json(
            {
                "destinations": [
                    {"destination": "email", "publisher_type": "smtp", "success_count": 90, "failure_count": 10, "last_success_at": "2026-05-27T00:00:00Z", "last_failure_at": "2026-05-27T01:00:00Z", "failure_rate_slo": 0.05},
                    {"destination": "webhook", "publisher_type": "http", "success_count": 0, "failure_count": 3, "last_success_at": "", "last_failure_at": "2026-05-27T01:00:00Z", "failure_rate_slo": 0.05},
                ]
            }
        )
    )

    assert [row["status"] for row in report["rows"]] == ["unavailable", "degraded"]
    assert report["rows"][1]["failure_rate"] == 0.1
    assert report["summary"]["degraded_destinations"] == 2
    assert report["summary"]["unavailable_destinations"] == 1
