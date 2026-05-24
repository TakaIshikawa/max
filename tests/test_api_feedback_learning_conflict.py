from __future__ import annotations

import json

from max.api.feedback_learning_conflict import feedback_learning_conflict_to_json


def test_feedback_learning_conflict_groups_approve_reject_by_scope() -> None:
    parsed = json.loads(
        feedback_learning_conflict_to_json(
            {
                "signals": [
                    {"id": "s1", "idea_id": "i1", "profile": "A", "dimension": "fit", "outcome": "approve"},
                    {"id": "s2", "idea_id": "i1", "profile": "A", "dimension": "fit", "outcome": "reject"},
                    {"id": "s3", "idea_id": "i1", "profile": "B", "dimension": "fit", "outcome": "approve"},
                ]
            }
        )
    )

    assert parsed["summary"]["status"] == "conflicted"
    assert parsed["conflict_groups"][0]["idea_id"] == "i1"
    assert parsed["conflict_groups"][0]["profile"] == "a"
    assert parsed["dimension_totals"][0]["dimension"] == "fit"


def test_feedback_learning_conflict_resolved_excluded_from_blockers() -> None:
    parsed = json.loads(feedback_learning_conflict_to_json({"feedback": [{"id": "a", "idea": "i", "decision": "approved", "resolved": True}, {"id": "b", "idea": "i", "decision": "rejected", "resolved": True}]}))

    assert parsed["summary"]["status"] == "clean"
    assert parsed["summary"]["resolved_conflict_count"] == 1
    assert parsed["summary"]["unresolved_count"] == 0
