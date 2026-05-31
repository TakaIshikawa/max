from __future__ import annotations

import json

from max.api import embedding_index_fragmentation_status_to_json


def test_embedding_index_fragmentation_status_flags_fragmented_indexes() -> None:
    payload = {"indexes": [{"index": "healthy", "total_vectors": 100, "stale_vectors": 1, "segment_count": 2}, {"index": "frag", "total_vectors": 100, "deleted_vectors": 40, "segment_count": 5, "pending_compactions": 1}]}

    data = json.loads(embedding_index_fragmentation_status_to_json(payload))

    assert [row["index"] for row in data["rows"]] == ["frag", "healthy"]
    assert data["rows"][0]["fragmentation_ratio"] == 0.4
    assert data["rows"][0]["recommended_action"] == "run_compaction"


def test_embedding_index_fragmentation_status_handles_zero_vectors() -> None:
    data = json.loads(embedding_index_fragmentation_status_to_json({"items": [{"name": "empty", "total_vectors": 0, "stale_vectors": 9}]}))

    assert data["rows"][0]["fragmentation_ratio"] == 0.0
    assert data["summary"]["index_count"] == 1
