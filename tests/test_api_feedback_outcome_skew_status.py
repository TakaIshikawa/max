from __future__ import annotations

import json

from max.api.feedback_outcome_skew_status import feedback_outcome_skew_status_to_json


def test_feedback_outcome_skew_status_balanced() -> None:
    feedback = [{"outcome": "approved"}, {"outcome": "rejected"}] * 5
    parsed = json.loads(feedback_outcome_skew_status_to_json({"feedback": feedback, "min_sample_size": 10}))

    assert parsed["summary"]["status"] == "healthy"


def test_feedback_outcome_skew_status_approval_and_rejection_skewed() -> None:
    approval = json.loads(feedback_outcome_skew_status_to_json({"feedback": [{"outcome": "approved"}] * 8 + [{"outcome": "rejected"}] * 2}))
    rejection = json.loads(feedback_outcome_skew_status_to_json({"feedback": [{"outcome": "rejected"}] * 8 + [{"outcome": "approved"}] * 2}))

    assert approval["summary"]["status"] == "critical"
    assert rejection["summary"]["status"] == "critical"


def test_feedback_outcome_skew_status_sparse_sample() -> None:
    parsed = json.loads(feedback_outcome_skew_status_to_json({"feedback": [{"outcome": "approved"}]}))

    assert parsed["summary"]["status"] == "insufficient_data"


def test_feedback_outcome_skew_status_rounding_and_group_order() -> None:
    parsed = json.loads(feedback_outcome_skew_status_to_json({"min_sample_size": 3, "feedback": [{"outcome": "approved", "reviewer": "b", "profile": "p2"}, {"outcome": "rejected", "reviewer": "a", "profile": "p1"}, {"outcome": "skipped", "reviewer": "a", "profile": "p1"}]}))

    assert sum(row["percentage"] for row in parsed["outcome_distribution"]) == 100.0
    assert [row["reviewer"] for row in parsed["reviewer_skew"]] == ["a", "b"]
