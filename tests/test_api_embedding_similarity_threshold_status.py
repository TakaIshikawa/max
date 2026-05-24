from __future__ import annotations

import json

from max.api import embedding_similarity_threshold_status_to_json


def test_embedding_similarity_threshold_status_classifies_profiles() -> None:
    parsed = json.loads(
        embedding_similarity_threshold_status_to_json(
            {
                "profiles": [
                    {"profile": "strict", "threshold": 0.93},
                    {"profile": "balanced", "threshold": 0.84},
                    {"profile": "loose", "threshold": 0.7},
                    {"profile": "drift", "threshold": 0.85, "false_positive_rate": 0.25},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["profiles"]] == ["drifting", "loose", "strict", "balanced"]
    assert parsed["summary"]["drifting_count"] == 1
    assert parsed["summary"]["balanced_count"] == 1


def test_embedding_similarity_threshold_status_clamps_invalid_numeric_inputs() -> None:
    parsed = json.loads(embedding_similarity_threshold_status_to_json({"thresholds": [{"profile": "p", "threshold": 2, "observed_match_rate": -1, "false_positive_hint": "bad"}]}))

    profile = parsed["profiles"][0]
    assert profile["threshold"] == 1.0
    assert profile["observed_match_rate"] == 0.0
    assert profile["false_positive_rate"] == 0.0

