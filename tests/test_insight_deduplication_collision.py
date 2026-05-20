from __future__ import annotations

import json

from max.exports.insight_deduplication_collision import (
    KIND,
    build_insight_deduplication_collision_report,
    render_insight_deduplication_collision_json,
)


def test_insight_deduplication_collision_builds_review_queue() -> None:
    report = build_insight_deduplication_collision_report(
        [
            {"insight_id": "i-2", "duplicate_of": "i-1", "similarity_score": "0.95", "source_ids": ["s2", "s1"], "profile": "growth", "title": "Same idea", "resolution": "open"},
            {"insight_id": "i-3", "duplicate_of": "i-1", "similarity_score": 0.72, "profile": "growth", "resolution": "merged"},
            {"insight_id": "i-4", "duplicate_of": "i-5", "similarity_score": 0.91, "profile": "ops", "resolution": "needs review"},
        ],
        similarity_threshold=0.9,
    )

    assert report["kind"] == KIND
    assert report["summary"]["collision_count"] == 3
    assert report["summary"]["high_similarity_count"] == 2
    assert report["summary"]["unresolved_count"] == 2
    assert report["collisions"][0]["source_ids"] == ["s1", "s2"]
    assert [row["insight_id"] for row in report["review_queue"]] == ["i-2", "i-4"]
    assert json.loads(render_insight_deduplication_collision_json(report))["similarity_threshold"] == 0.9


def test_insight_deduplication_collision_defaults_missing_fields() -> None:
    report = build_insight_deduplication_collision_report([{}])

    row = report["collisions"][0]
    assert row["insight_id"] == "unknown-insight-1"
    assert row["title"] == "Untitled insight"
    assert row["source_ids"] == ["unknown-source"]
    assert report["review_queue"][0]["unresolved"] is True
