from __future__ import annotations

import json

from max.api.feedback_learning_queue_status import feedback_learning_queue_status_to_json


def test_feedback_learning_queue_status_derives_queue_states_and_priority() -> None:
    parsed = json.loads(
        feedback_learning_queue_status_to_json(
            {
                "items": [
                    {"feedback_id": "q", "profile": "p", "outcome": "accepted", "priority": "urgent"},
                    {"feedback_id": "p", "profile": "p", "outcome": "accepted", "state": "processing"},
                    {"feedback_id": "d", "profile": "q", "outcome": "rejected", "age_hours": 24, "priority": "weird"},
                    {"feedback_id": "f", "profile": "q", "outcome": "rejected", "attempts": 3, "last_error": "timeout"},
                ]
            }
        )
    )

    assert [row["feedback_id"] for row in parsed["items"]] == ["f", "d", "p", "q"]
    assert [row["status"] for row in parsed["items"]] == ["failed", "delayed", "processing", "queued"]
    assert parsed["items"][1]["priority"] == "normal"
    assert parsed["summary"]["failed_count"] == 1
    assert parsed["profile_totals"][1]["failed_count"] == 1


def test_feedback_learning_queue_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(feedback_learning_queue_status_to_json({"queue": [{"id": "x", "profile": "p", "outcome": "o", "error": "bad", "attempt_count": 1}]}, as_of="now"))

    assert parsed["failed_items"][0]["feedback_id"] == "x"
    assert parsed["outcome_totals"][0]["outcome"] == "o"
    assert parsed["metadata"]["as_of"] == "now"
