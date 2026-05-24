from __future__ import annotations

import json

from max.api.feedback_learning_status import KIND, SCHEMA_VERSION, feedback_learning_status_to_json


def test_feedback_learning_status_groups_outcomes_and_profiles() -> None:
    payload = {
        "feedback_outcomes": [
            {"feedback_id": "f2", "outcome": "rejected", "profile": "beta", "confidence_delta": -0.1},
            {"feedback_id": "f1", "outcome": "accepted", "profile": "alpha", "confidence_delta": 0.2},
            {"feedback_id": "f3", "outcome": "needs_review", "profile": "alpha"},
        ],
        "weight_adjustments": [{"dimension": "risk", "previous_weight": 0.2, "current_weight": 0.3}],
    }

    parsed = json.loads(feedback_learning_status_to_json(payload))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"approval_count": 1, "neutral_count": 1, "rejection_count": 1, "total_count": 3}
    assert [row["feedback_id"] for row in parsed["outcomes"]] == ["f1", "f2", "f3"]
    assert parsed["weight_adjustments"] == [{"current_weight": 0.3, "delta": 0.1, "dimension": "risk", "previous_weight": 0.2, "reason": None}]
    assert parsed["affected_profiles"] == [
        {"feedback_ids": ["f1", "f3"], "outcome_count": 2, "profile": "alpha"},
        {"feedback_ids": ["f2"], "outcome_count": 1, "profile": "beta"},
    ]
    assert feedback_learning_status_to_json(payload) == feedback_learning_status_to_json({"feedback_outcomes": list(reversed(payload["feedback_outcomes"])), "weight_adjustments": payload["weight_adjustments"]})


def test_feedback_learning_status_honors_explicit_sections() -> None:
    parsed = json.loads(
        feedback_learning_status_to_json(
            {
                "outcomes": [{}],
                "summary": {"approval_count": 8},
                "affected_profiles": [{"profile": "manual", "feedback_ids": ["f"]}],
                "anomalies": [{"id": "n1"}],
                "learning_window": {"started_at": "s", "ended_at": "e", "feedback_count": 3},
                "next_actions": [{"id": "a"}],
            }
        )
    )

    assert parsed["summary"]["approval_count"] == 8
    assert parsed["affected_profiles"][0]["profile"] == "manual"
    assert parsed["anomalies"][0]["id"] == "n1"
    assert parsed["learning_window"]["feedback_count"] == 3
    assert parsed["next_actions"][0]["id"] == "a"
