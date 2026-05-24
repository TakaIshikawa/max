from __future__ import annotations

import json

from max.api.feedback_outcome_intake import feedback_outcome_intake_to_json


def test_feedback_outcome_intake_normalizes_outcome_aliases_and_totals() -> None:
    parsed = json.loads(
        feedback_outcome_intake_to_json(
            {
                "outcomes": [
                    {"id": "f1", "status": "approve", "profile": "sales", "reviewer": "ana", "weight_delta": "0.2"},
                    {"id": "f2", "result": "declined", "profile": "sales", "reviewer": "ana", "weight_delta": -0.1},
                    {"id": "f3", "outcome": "done", "profile": "support"},
                    {"id": "f4", "outcome": "defer", "reviewer": "ben"},
                ]
            }
        )
    )

    assert parsed["summary"]["approved_count"] == 1
    assert parsed["summary"]["rejected_count"] == 1
    assert parsed["summary"]["completed_count"] == 1
    assert parsed["summary"]["deferred_count"] == 1
    assert parsed["profile_totals"][0]["profile"] == "sales"


def test_feedback_outcome_intake_preserves_invalid_record_reasons() -> None:
    parsed = json.loads(feedback_outcome_intake_to_json({"feedback": [{"id": "bad", "outcome": "maybe"}, "raw"]}))

    assert parsed["summary"]["invalid_count"] == 2
    assert parsed["invalid_records"][0]["id"] == "F2"
    assert parsed["invalid_records"][1]["reason"] == "unknown outcome"


def test_feedback_outcome_intake_queues_and_weight_candidates_are_stable() -> None:
    parsed = json.loads(
        feedback_outcome_intake_to_json(
            {"feedback_records": [{"id": "b", "outcome": "approved", "profile": "p", "weight_delta": 0.1}, {"id": "a", "outcome": "deferred", "reviewer": "r"}]},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["reviewer_queues"] == [{"feedback_ids": ["a"], "pending_count": 1, "reviewer": "r"}]
    assert parsed["weight_update_candidates"] == [{"id": "b", "outcome": "approved", "profile": "p", "weight_delta": 0.1}]
    assert set(parsed) == {"schema_version", "kind", "summary", "accepted_outcomes", "invalid_records", "profile_totals", "reviewer_queues", "weight_update_candidates", "metadata"}
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
