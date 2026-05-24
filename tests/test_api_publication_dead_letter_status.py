from __future__ import annotations

import json

from max.api.publication_dead_letter_status import publication_dead_letter_status_to_json


def test_publication_dead_letter_status_derives_retry_states() -> None:
    parsed = json.loads(
        publication_dead_letter_status_to_json(
            {
                "messages": [
                    {"message_id": "retry", "destination": "email", "idea_id": "i1", "attempts": 1, "max_attempts": 3, "retryable": True},
                    {"message_id": "done", "destination": "email", "idea_id": "i1", "attempts": 3, "max_attempts": 3},
                    {"message_id": "block", "destination": "slack", "idea_id": "i2", "attempts": -1, "max_attempts": "bad", "retryable": "false"},
                    {"message_id": "arch", "destination": "slack", "idea_id": "i2", "archived": True},
                ]
            }
        )
    )

    assert [row["message_id"] for row in parsed["messages"]] == ["done", "block", "retry", "arch"]
    assert parsed["messages"][1]["attempts"] == 0
    assert parsed["messages"][1]["max_attempts"] == 1
    assert parsed["summary"]["exhausted_count"] == 1
    assert parsed["destination_totals"][0]["exhausted_count"] == 1


def test_publication_dead_letter_status_aliases_error_totals_and_metadata() -> None:
    parsed = json.loads(publication_dead_letter_status_to_json({"dead_letters": [{"id": "m", "destination": "d", "error": "timeout", "attempt_count": 2, "attempt_limit": 2}]}, as_of="now"))

    assert parsed["exhausted_messages"][0]["last_error"] == "timeout"
    assert parsed["error_totals"][0]["last_error"] == "timeout"
    assert parsed["metadata"]["as_of"] == "now"
