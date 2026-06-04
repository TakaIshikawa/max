from __future__ import annotations

import json

from max.api.feedback_reviewer_queue_balance_status import feedback_reviewer_queue_balance_status_to_json


def test_feedback_reviewer_queue_balance_status_excludes_closed_and_unassigned() -> None:
    report = json.loads(
        feedback_reviewer_queue_balance_status_to_json(
            [
                {"reviewer_id": "a", "status": "open"},
                {"reviewer_id": "a", "status": "resolved"},
                {"reviewer_id": "a", "status": "open"},
                {"reviewer_id": "b", "status": "open"},
                {"status": "open"},
            ],
            overload_threshold=1,
        )
    )

    assert [row["reviewer_id"] for row in report["reviewers"]] == ["a", "b", "unassigned"]
    assert report["summary"]["total_open"] == 4
    assert report["summary"]["overloaded_reviewers"] == ["a"]

