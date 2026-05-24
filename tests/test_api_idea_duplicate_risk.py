from __future__ import annotations

import json

from max.api.idea_duplicate_risk import idea_duplicate_risk_to_json


def test_idea_duplicate_risk_clamps_similarity_and_counts_profiles() -> None:
    parsed = json.loads(
        idea_duplicate_risk_to_json(
            {
                "ideas": [
                    {"id": "b", "profile": "Ops", "evidence_ids": ["e1", "e2", "e3"]},
                    {"id": "a", "profile": "Ops", "evidence_ids": ["e1", "e2", "e3"]},
                ],
                "pairs": [{"idea_a": "a", "idea_b": "b", "similarity": 2}],
            }
        )
    )

    assert parsed["summary"]["status"] == "critical"
    assert parsed["top_risky_pairs"][0]["similarity"] == 1.0
    assert parsed["top_risky_pairs"][0]["shared_evidence_count"] == 3
    assert parsed["profile_counts"][0]["profile"] == "ops"


def test_idea_duplicate_risk_handles_missing_evidence_ids() -> None:
    parsed = json.loads(idea_duplicate_risk_to_json({"ideas": [{"id": "a"}, {"id": "b"}], "pairs": [{"idea_ids": ["a", "b"], "score": 0.7}]}))

    assert parsed["top_risky_pairs"][0]["status"] == "medium"
    assert parsed["top_risky_pairs"][0]["shared_evidence_ids"] == []


def test_idea_duplicate_risk_orders_by_severity_similarity_and_idea_id() -> None:
    parsed = json.loads(
        idea_duplicate_risk_to_json(
            {
                "ideas": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
                "similarities": [
                    {"idea_a": "c", "idea_b": "d", "similarity": 0.8},
                    {"idea_a": "a", "idea_b": "b", "similarity": 0.9},
                    {"idea_a": "a", "idea_b": "c", "similarity": 0.9},
                ],
            }
        )
    )

    assert [row["idea_ids"] for row in parsed["top_risky_pairs"]] == [["a", "b"], ["a", "c"], ["c", "d"]]


def test_idea_duplicate_risk_empty_input_is_low_risk() -> None:
    parsed = json.loads(idea_duplicate_risk_to_json({}))

    assert parsed["summary"]["idea_count"] == 0
    assert parsed["summary"]["pair_count"] == 0
    assert parsed["summary"]["status"] == "low"
    assert parsed["top_risky_pairs"] == []
