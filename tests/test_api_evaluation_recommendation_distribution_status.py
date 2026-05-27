from __future__ import annotations

import json

from max.api import evaluation_recommendation_distribution_status_to_json


def test_evaluation_recommendation_distribution_status_counts_and_flags_skew() -> None:
    parsed = json.loads(evaluation_recommendation_distribution_status_to_json({"expected_max": 0.6, "evaluations": [{"idea_id": "a", "profile": "P", "evaluator": "E", "recommendation": "approve"}, {"idea_id": "b", "profile": "P", "evaluator": "E", "decision": "approve"}, {"idea_id": "c", "profile": "P", "evaluator": "E", "recommendation": "reject"}]}))

    assert parsed["schema_version"] == "max.api.evaluation_recommendation_distribution_status.v1"
    assert parsed["summary"]["evaluation_count"] == 3
    assert parsed["summary"]["recommendation_counts"]["approve"] == 2
    assert parsed["summary"]["skewed_bucket_count"] >= 1
    assert parsed["distributions"][0]["skewed"] is True
