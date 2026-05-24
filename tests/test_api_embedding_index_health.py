from __future__ import annotations

import json

from max.api.embedding_index_health import embedding_index_health_to_json


def test_embedding_index_health_derives_status_and_detects_mismatches() -> None:
    parsed = json.loads(
        embedding_index_health_to_json(
            {
                "indexes": [
                    {"name": "healthy", "provider": "openai", "model": "a", "vector_count": "10", "dimension": 1536},
                    {"name": "bad-dim", "provider": "openai", "model": "b", "expected_dimension": 1536, "actual_dimension": 1024},
                    {"name": "stale", "stale": "true", "vectors": "5"},
                ]
            }
        )
    )

    assert parsed["summary"]["overall_status"] == "dimension_mismatch"
    assert [row["index_name"] for row in parsed["degraded_indexes"]] == ["bad-dim", "stale"]
    assert parsed["summary"]["vector_count"] == 15


def test_embedding_index_health_normalizes_progress_and_malformed_counts() -> None:
    parsed = json.loads(embedding_index_health_to_json({"embedding_indexes": [{"name": "rebuild", "rebuild_progress": "45", "vector_count": "bad"}]}))

    assert parsed["indexes"][0]["rebuild_progress"] == 0.45
    assert parsed["indexes"][0]["vector_count"] == 0
    assert parsed["rebuilds"][0]["index_name"] == "rebuild"


def test_embedding_index_health_provider_totals_next_actions_and_metadata() -> None:
    parsed = json.loads(
        embedding_index_health_to_json(
            {"schema_version": "source.v1", "kind": "source.kind", "indexes": [{"name": "x", "provider": "p", "model": "m", "degraded": True}]},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["provider_totals"] == [{"index_count": 1, "model": "m", "provider": "p", "vector_count": 0}]
    assert parsed["next_actions"][0]["id"] == "repair-x"
    assert set(parsed) == {"schema_version", "kind", "summary", "indexes", "degraded_indexes", "provider_totals", "rebuilds", "next_actions", "metadata"}
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
