from __future__ import annotations

import json

from max.api import publication_destination_latency_slo_status_to_json


def test_publication_destination_latency_slo_status_classifies_breaches() -> None:
    data = json.loads(publication_destination_latency_slo_status_to_json({"slo_ms": 1000, "critical_multiplier": 2, "destinations": [{"destination": "slack", "p50_ms": 100, "p95_ms": 900, "p99_ms": 2500, "sample_count": 10}, {"destination": "jira", "p50_ms": 100, "p95_ms": 1200, "p99_ms": 1500, "sample_count": 5}, {"destination": "email", "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "sample_count": 0}]}))

    assert data["status"] == "critical"
    assert data["summary"]["destination_count"] == 3
    assert data["summary"]["breached_destination_count"] == 3
    assert data["summary"]["max_p95_ms"] == 1200.0
    assert data["summary"]["max_p99_ms"] == 2500.0
    assert [row["status"] for row in data["destinations"]] == ["critical", "critical", "warning"]
