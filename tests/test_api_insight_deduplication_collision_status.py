from __future__ import annotations

import json

from max.api import insight_deduplication_collision_status_to_json


def test_insight_deduplication_collision_status_flags_candidates() -> None:
    parsed = json.loads(
        insight_deduplication_collision_status_to_json(
            {
                "candidates": [
                    {"id": "safe", "labels": ["A"], "confidence_delta": 0.05, "evidence_overlap": 0.9},
                    {"id": "review", "labels": ["A", "B"], "confidence_delta": 0.05, "evidence_overlap": 0.8},
                    {"id": "hard", "labels": ["A", "B"], "confidence_delta": 0.4, "evidence_overlap": 0.4},
                ]
            }
        )
    )

    assert [row["candidate_id"] for row in parsed["candidates"]] == ["hard", "review", "safe"]
    assert parsed["summary"]["collision_count"] == 1
    assert parsed["candidates"][0]["confidence_delta"] == 0.4

