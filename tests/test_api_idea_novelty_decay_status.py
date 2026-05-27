from __future__ import annotations

import json

from max.api import idea_novelty_decay_status_to_json


def test_idea_novelty_decay_status_marks_and_sorts_stale_ideas() -> None:
    report = json.loads(idea_novelty_decay_status_to_json({"decay_threshold": 0.8, "ideas": [{"idea_id": "fresh", "profile": "Growth", "similarity_score": 0.42}, {"idea_id": "stale-b", "profile": "Ops", "similarity_score": 0.91, "generated_at": "2026-05-01", "last_similar_seen_at": "2026-05-20"}, {"idea_id": "stale-a", "profile": "Ops", "similarity_score": 0.91}]}))

    assert report["schema_version"] == "max.api.idea_novelty_decay_status.v1"
    assert [row["idea_id"] for row in report["rows"]] == ["stale-a", "stale-b", "fresh"]
    assert [row["idea_id"] for row in report["stale_ideas"]] == ["stale-a", "stale-b"]
    assert report["summary"] == {"status": "stale_ideas", "idea_count": 3, "stale_count": 2, "max_similarity_score": 0.91}
