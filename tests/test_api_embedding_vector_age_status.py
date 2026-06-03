from __future__ import annotations

import json

from max.api import embedding_vector_age_status_to_json


def test_embedding_vector_age_status_computes_stale_rate_and_model_mismatch() -> None:
    data = json.loads(embedding_vector_age_status_to_json({"indexes": [{"index": "a", "vector_count": 100, "stale_vector_count": 30, "oldest_vector_age_days": 20, "embedding_model": "old", "expected_model": "new"}, {"index": "b", "vector_count": 100, "stale_vector_count": 12, "embedding_model": "new", "expected_model": "new"}, {"index": "c", "vector_count": 0, "stale_vector_count": 2}]}))
    assert data["summary"] == {"status": "critical", "index_count": 3, "stale_index_count": 2, "model_mismatch_count": 1, "critical_count": 1, "warning_count": 1, "max_stale_rate": 0.3}
    assert [row["index"] for row in data["indexes"]] == ["a", "b", "c"]
    assert data["indexes"][0]["model_mismatch"] is True
    assert data["indexes"][2]["stale_rate"] == 0.0
