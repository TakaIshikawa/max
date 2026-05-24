from __future__ import annotations

import json

from max.api.source_fetch_allocation_status import source_fetch_allocation_status_to_json


def test_source_fetch_allocation_status_computes_drift_and_recommendations() -> None:
    parsed = json.loads(
        source_fetch_allocation_status_to_json(
            {
                "drift_threshold": 0.1,
                "sources": [
                    {"source": "alpha", "requested": 50, "actual": 80, "target_share": 0.5},
                    {"source": "beta", "requested": 50, "actual": 20, "target_share": 0.5},
                ],
            }
        )
    )

    assert parsed["summary"]["actual_count"] == 100
    assert parsed["sources"][0]["source"] == "alpha"
    assert parsed["sources"][0]["drift_from_target"] == 0.3
    assert parsed["overallocated_sources"][0]["source"] == "alpha"
    assert parsed["underallocated_sources"][0]["source"] == "beta"
    assert {row["action"] for row in parsed["next_adjustment_recommendations"]} == {"Reduce next fetch allocation", "Increase next fetch allocation"}


def test_source_fetch_allocation_status_aliases_and_suppression() -> None:
    parsed = json.loads(
        source_fetch_allocation_status_to_json(
            {
                "allocations": [
                    {"name": "news", "requested_fetches": "10", "actual_fetches": "0", "target": "50", "circuit_breaker_open": "true", "reason": "429s"},
                    {"name": "docs", "requested_fetches": "10", "fetched": "20", "target": "50"},
                ],
                "metadata": {"run": "r1"},
            },
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["suppressed_sources"][0]["source"] == "news"
    assert parsed["suppressed_sources"][0]["suppression_reason"] == "429s"
    assert parsed["metadata"]["run"] == "r1"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"


def test_source_fetch_allocation_status_handles_missing_totals() -> None:
    parsed = json.loads(source_fetch_allocation_status_to_json({"sources": [{"source": "empty"}]}))

    assert parsed["sources"][0]["requested_share"] == 0.0
    assert parsed["sources"][0]["actual_share"] == 0.0
    assert parsed["sources"][0]["drift_from_target"] == 0.0
