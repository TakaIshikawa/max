from __future__ import annotations

import json

from max.api import signal_deduplication_cluster_status_to_json


def test_signal_deduplication_cluster_status_normalizes_and_sorts() -> None:
    parsed = json.loads(
        signal_deduplication_cluster_status_to_json(
            {
                "clusters": [
                    {"id": "healthy", "signals": 10, "duplicates": 1, "sources": ["web", "email"], "source_coverage": 0.7},
                    {"id": "crowded", "signal_count": 10, "duplicate_count": 50, "source_coverage": 2},
                    {"id": "watch", "signal_count": 10, "duplicate_ratio": 0.25, "source_coverage": 0.8},
                ]
            },
            as_of="2026-05-24T00:00:00Z",
        )
    )

    assert [row["cluster_id"] for row in parsed["clusters"]] == ["crowded", "watch", "healthy"]
    assert parsed["clusters"][0]["duplicate_count"] == 10
    assert parsed["clusters"][0]["source_coverage"] == 1.0
    assert parsed["summary"]["crowded_count"] == 1
    assert parsed["summary"]["watch_count"] == 1
    assert parsed["metadata"]["as_of"] == "2026-05-24T00:00:00Z"


def test_signal_deduplication_cluster_status_handles_missing_optional_fields() -> None:
    parsed = json.loads(signal_deduplication_cluster_status_to_json({"deduplication_clusters": [{}]}))

    assert parsed["clusters"][0]["cluster_id"] == "cluster-1"
    assert parsed["clusters"][0]["status"] == "healthy"
    assert parsed["source_totals"][0]["source"] == "unknown-source"
