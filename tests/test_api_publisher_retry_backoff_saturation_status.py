from __future__ import annotations

import json

from max.api import publisher_retry_backoff_saturation_status_to_json


def test_publisher_retry_backoff_saturation_status_summarizes_and_sorts() -> None:
    data = json.loads(publisher_retry_backoff_saturation_status_to_json({"destinations": [{"destination": "email", "queued_retry_count": 3, "max_retry_delay_seconds": 100, "current_retry_delay_seconds": 80, "retry_budget_remaining": 2, "oldest_retry_age_minutes": 30}, {"destination": "slack", "queued_retry_count": 5, "max_retry_delay_seconds": 100, "current_retry_delay_seconds": 95, "retry_budget_remaining": 1, "oldest_retry_age_minutes": 10}, {"destination": "webhook", "queued_retry_count": 1, "retry_budget_remaining": 0, "oldest_retry_age_minutes": 60}]}))
    assert data["summary"] == {"status": "critical", "destination_count": 3, "saturated_destination_count": 3, "critical_count": 2, "warning_count": 1, "total_queued_retry_count": 9, "max_backoff_ratio": 0.95}
    assert [row["destination"] for row in data["destinations"]] == ["webhook", "slack", "email"]
    assert data["destinations"][0]["backoff_ratio"] == 0.0
