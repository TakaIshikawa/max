from __future__ import annotations

import json

from max.api import publisher_destination_failover_status_to_json


def test_publisher_destination_failover_status_reports_fallback_and_failure_counts() -> None:
    rendered = json.loads(publisher_destination_failover_status_to_json({"destinations": [{"destination": "email", "primary_status": "healthy", "fallback_status": "healthy", "failover_success_count": 3}, {"destination": "webhook", "primary_status": "down", "fallback_status": "failed", "failover_failure_count": 2}]}))

    assert rendered["schema_version"] == "max.api.publisher_destination_failover_status.v1"
    assert rendered["kind"] == "max.api.publisher_destination_failover_status"
    assert rendered["summary"] == {"destination_count": 2, "missing_fallback_count": 1, "failed_failover_count": 2, "status": "critical"}
    assert rendered["destinations_without_healthy_fallback"][0]["destination"] == "webhook"
    assert rendered["destinations"][0]["failover_success_rate"] == 1.0
