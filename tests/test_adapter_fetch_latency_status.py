from __future__ import annotations

import json

from max.api.adapter_fetch_latency_status import adapter_fetch_latency_status_to_json


def test_adapter_fetch_latency_status_reports_healthy_latency() -> None:
    report = json.loads(adapter_fetch_latency_status_to_json({"adapters": [{"adapter": "rss", "source": "blog", "p50_ms": 40, "p95_ms": 120, "p99_ms": 250, "sample_count": 20}]}))

    assert report["adapters"][0]["p95_ms"] == 120
    assert report["adapters"][0]["threshold_breaches"] == []
    assert report["adapters"][0]["status"] == "healthy"


def test_adapter_fetch_latency_status_flags_p95_breach() -> None:
    report = json.loads(adapter_fetch_latency_status_to_json({"adapters": [{"adapter": "api", "source": "crm", "p95_ms": 1500, "p99_ms": 1800, "sample_count": 5}]}))

    assert report["summary"]["status"] == "degraded"
    assert report["adapters"][0]["threshold_breaches"] == ["p95"]


def test_adapter_fetch_latency_status_flags_p99_breach_and_idle() -> None:
    report = json.loads(adapter_fetch_latency_status_to_json({"adapters": [{"adapter": "slow", "source": "erp", "p95_ms": 1500, "p99_ms": 2500, "sample_count": 8}, {"adapter": "empty", "source": "queue", "p95_ms": 9999, "p99_ms": 9999, "sample_count": 0}]}))

    assert report["adapters"][0]["status"] == "critical"
    assert report["adapters"][0]["threshold_breaches"] == ["p95", "p99"]
    assert report["adapters"][1]["status"] == "idle"


def test_adapter_fetch_latency_status_sorts_breaches_then_adapter() -> None:
    report = json.loads(adapter_fetch_latency_status_to_json({"adapters": [{"adapter": "z", "source": "b", "p95_ms": 10, "p99_ms": 20, "sample_count": 1}, {"adapter": "a", "source": "a", "p95_ms": 10, "p99_ms": 3000, "sample_count": 1}]}))

    assert [row["adapter"] for row in report["adapters"]] == ["a", "z"]
