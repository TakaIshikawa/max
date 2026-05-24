from __future__ import annotations

import json

from max.api.insight_deduplication_status import insight_deduplication_status_to_json


def test_insight_deduplication_status_clamps_thresholds_and_extracts_reviews() -> None:
    parsed = json.loads(
        insight_deduplication_status_to_json(
            {
                "similarity_threshold": "1.5",
                "clusters": [
                    {"id": "c-low", "canonical_id": "i1", "profile": "sales", "category": "pricing", "duplicates": ["d1"], "score": "0.7"},
                    {"id": "c-high", "canonical_id": "i2", "profile": "sales", "category": "risk", "duplicate_count": 2, "score": "2"},
                ],
            }
        )
    )

    assert parsed["summary"]["review_threshold"] == 1.0
    assert [row["cluster_id"] for row in parsed["review_needed"]] == ["c-low"]
    assert parsed["clusters"][1]["similarity_score"] == 1.0


def test_insight_deduplication_status_derives_summary_and_stable_ids() -> None:
    parsed = json.loads(
        insight_deduplication_status_to_json(
            {
                "review_threshold": 0.85,
                "dedupe_clusters": [
                    {"profile": "support", "category": "handoff", "duplicates": ["b", "a"], "similarity_score": 0.8},
                    {"cluster_id": "z", "canonical_insight_id": "cz", "duplicate_count": "3", "similarity_score": 0.9},
                ],
            }
        )
    )

    assert parsed["clusters"][0]["cluster_id"] == "cluster-1"
    assert parsed["clusters"][0]["duplicate_ids"] == ["a", "b"]
    assert parsed["summary"]["duplicate_count"] == 5
    assert parsed["profile_totals"][0]["profile"] == "support"


def test_insight_deduplication_status_metadata_and_deterministic_json() -> None:
    payload = {"schema_version": "source.v1", "kind": "source.kind", "clusters": []}
    parsed = json.loads(insight_deduplication_status_to_json(payload, as_of="2026-05-21T00:00:00Z"))

    assert set(parsed) == {"schema_version", "kind", "summary", "clusters", "review_needed", "profile_totals", "category_totals", "metadata"}
    assert parsed["metadata"]["source_kind"] == "source.kind"
    assert insight_deduplication_status_to_json(payload) == insight_deduplication_status_to_json(payload)
