from __future__ import annotations

import json

from max.api import feedback_reviewer_workload_status_to_json


def test_reviewer_workload_classifies_zero_capacity_and_hot_spots() -> None:
    report = json.loads(feedback_reviewer_workload_status_to_json({"reviewers": [{"reviewer": "ann", "pending_reviews": 4, "capacity": 0, "profiles": ["core"]}, {"reviewer": "bob", "pending_reviews": 8, "capacity": 10, "profiles": ["core", "growth"]}, {"reviewer": "cy", "pending_reviews": 1, "capacity": 10}]}))

    assert report["reviewers"][0]["reviewer"] == "ann"
    assert report["reviewers"][0]["status"] == "critical"
    assert report["summary"]["overloaded_count"] == 2
    assert report["profile_hot_spots"][0]["profile"] == "core"
