from __future__ import annotations

import json

from max.api import publisher_webhook_latency_status_to_json as exported
from max.api.publisher_webhook_latency_status import publisher_webhook_latency_status_to_json


def test_publisher_webhook_latency_status_handles_empty_samples() -> None:
    report = json.loads(publisher_webhook_latency_status_to_json([]))

    assert exported is publisher_webhook_latency_status_to_json
    assert report["summary"]["status"] == "healthy"
    assert report["webhooks"] == []


def test_publisher_webhook_latency_status_computes_deterministic_percentiles() -> None:
    report = json.loads(publisher_webhook_latency_status_to_json([{"destination": "crm", "event_type": "lead", "latency_ms": 10}, {"destination": "crm", "event_type": "lead", "latency_ms": 20}, {"destination": "crm", "event_type": "lead", "latency_ms": 30}, {"destination": "crm", "event_type": "lead", "latency_ms": 40}]))

    assert report["webhooks"][0]["sample_count"] == 4
    assert report["webhooks"][0]["p50_latency_ms"] == 25
    assert report["webhooks"][0]["p95_latency_ms"] == 38.5
    assert report["webhooks"][0]["status"] == "healthy"


def test_publisher_webhook_latency_status_marks_timeouts_first() -> None:
    report = json.loads(publisher_webhook_latency_status_to_json([{"destination": "slow", "event": "x", "duration_ms": 2000}, {"destination": "timeout", "event": "x", "latency_ms": 1, "timeout": True}], slow_p95_ms=1000))

    assert [row["status"] for row in report["webhooks"]] == ["timing_out", "slow"]
    assert report["summary"]["status"] == "timing_out"
