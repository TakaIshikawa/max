from __future__ import annotations

import json

from max.api.source_fetch_latency import source_fetch_latency_to_json


def test_source_fetch_latency_percentiles_are_deterministic_for_small_samples() -> None:
    parsed = json.loads(source_fetch_latency_to_json({"sla_ms": 250, "sources": [{"source": "a", "latencies_ms": [100, 200, 300]}]}))

    assert parsed["sources"][0]["p50_latency_ms"] == 200
    assert parsed["sources"][0]["p95_latency_ms"] == 300
    assert parsed["sources"][0]["status"] == "slow"
    assert parsed["summary"]["status"] == "slow"


def test_source_fetch_latency_timeout_drives_status() -> None:
    parsed = json.loads(source_fetch_latency_to_json({"fetches": [{"source": "b", "latencies": [10], "timeout_count": 1}, {"source": "a", "latencies": [500], "sla_ms": 100}]}))

    assert [row["source"] for row in parsed["sources"]] == ["b", "a"]
    assert parsed["summary"]["status"] == "timed_out"
    assert parsed["summary"]["timeout_count"] == 1
