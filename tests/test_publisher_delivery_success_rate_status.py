from __future__ import annotations

import json

from max.api.publisher_delivery_success_rate_status import publisher_delivery_success_rate_status_to_json


def test_publisher_delivery_success_rate_status_healthy_and_empty() -> None:
    report = json.loads(publisher_delivery_success_rate_status_to_json({"destinations": [{"destination": "slack", "channel": "alerts", "delivered": 99, "failed": 1}]}))
    empty = json.loads(publisher_delivery_success_rate_status_to_json({"destinations": []}))

    assert report["destinations"][0]["success_rate"] == 0.99
    assert report["destinations"][0]["status"] == "healthy"
    assert empty["summary"]["success_rate"] == 1.0
    assert empty["summary"]["status"] == "healthy"


def test_publisher_delivery_success_rate_status_degraded_and_critical() -> None:
    report = json.loads(publisher_delivery_success_rate_status_to_json({"destinations": [{"destination": "email", "channel": "digest", "delivered": 90, "failed": 10}, {"destination": "webhook", "channel": "events", "delivered": 70, "failed": 30}]}))

    assert {row["destination"]: row["status"] for row in report["destinations"]} == {"email": "degraded", "webhook": "critical"}
    assert report["summary"]["status"] == "critical"


def test_publisher_delivery_success_rate_status_sorts_by_destination_then_channel() -> None:
    report = json.loads(publisher_delivery_success_rate_status_to_json({"destinations": [{"destination": "b", "channel": "z"}, {"destination": "a", "channel": "z"}, {"destination": "a", "channel": "a"}]}))

    assert [(row["destination"], row["channel"]) for row in report["destinations"]] == [("a", "a"), ("a", "z"), ("b", "z")]
