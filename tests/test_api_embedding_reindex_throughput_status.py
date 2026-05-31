from __future__ import annotations

import json

from max.api.embedding_reindex_throughput_status import embedding_reindex_throughput_status_to_json


def test_embedding_reindex_throughput_status_normal_throughput() -> None:
    parsed = json.loads(embedding_reindex_throughput_status_to_json({"queued_items": 100, "processed_items": 50, "processing_rate_per_minute": 10}))

    assert parsed["summary"]["status"] == "healthy"
    assert parsed["estimated_completion"]["minutes"] == 10.0


def test_embedding_reindex_throughput_status_stalled_queue() -> None:
    parsed = json.loads(embedding_reindex_throughput_status_to_json({"queued_items": 10, "processing_rate_per_minute": 5, "workers": [{"worker_id": "w1", "stalled": True}]}))

    assert parsed["summary"]["status"] == "critical"
    assert parsed["summary"]["stalled_worker_count"] == 1


def test_embedding_reindex_throughput_status_empty_queue() -> None:
    parsed = json.loads(embedding_reindex_throughput_status_to_json({"queued_items": 0, "processing_rate_per_minute": 0}))

    assert parsed["summary"]["status"] == "healthy"


def test_embedding_reindex_throughput_status_zero_rate_unavailable_eta() -> None:
    parsed = json.loads(embedding_reindex_throughput_status_to_json({"queued_items": 10, "processing_rate_per_minute": 0}))

    assert parsed["summary"]["status"] == "critical"
    assert parsed["estimated_completion"]["status"] == "unavailable"


def test_embedding_reindex_throughput_status_eta_formatting() -> None:
    parsed = json.loads(embedding_reindex_throughput_status_to_json({"queued_items": 10, "processing_rate_per_minute": 3}))

    assert parsed["estimated_completion"] == {"minutes": 3.33, "status": "available"}
