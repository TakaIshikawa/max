from __future__ import annotations

import json

from max.api import profile_constraint_conflict_status_to_json


def test_profile_constraint_conflict_status_normalizes_and_sorts() -> None:
    data = json.loads(profile_constraint_conflict_status_to_json({"profiles": [{"profile": "core", "constraint_count": 4, "conflict_count": 2, "unresolved_conflict_count": 1, "affected_sources": "rss", "affected_categories": ["cost", "quality"]}, {"profile": "growth", "conflict_count": 3, "affected_sources": ["web", "rss"]}, {"profile": "ops"}]}))
    assert data["summary"] == {"status": "critical", "profile_count": 3, "conflicted_profile_count": 2, "unresolved_profile_count": 1, "total_conflict_count": 5, "total_unresolved_conflict_count": 1}
    assert [row["profile"] for row in data["profiles"]] == ["core", "growth", "ops"]
    assert data["profiles"][0]["affected_sources"] == ["rss"]
    assert data["profiles"][1]["affected_sources"] == ["rss", "web"]
