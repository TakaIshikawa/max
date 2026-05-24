from __future__ import annotations

import json

from max.api.review_assignment_queue import (
    KIND,
    SCHEMA_VERSION,
    review_assignment_queue_to_json,
)


def test_review_assignment_queue_to_json_summarizes_assignments() -> None:
    payload = {
        "schema_version": "max.review_assignment_queue.v1",
        "kind": "max.review_assignment_queue",
        "assignments": [
            {
                "id": "r2",
                "reviewer": "mika",
                "status": "assigned",
                "priority": "high",
                "assigned_at": "2026-05-18T00:00:00Z",
                "due_at": "2026-05-22T00:00:00Z",
            },
            {
                "id": "r1",
                "status": "assigned",
                "priority": "normal",
                "assigned_at": "2026-05-20T00:00:00Z",
                "due_at": "2026-05-26T00:00:00Z",
            },
            {
                "id": "r3",
                "reviewer": "alex",
                "status": "done",
                "priority": "urgent",
                "assigned_at": "2026-05-10T00:00:00Z",
                "due_at": "2026-05-15T00:00:00Z",
            },
        ],
    }

    output = review_assignment_queue_to_json(payload, as_of="2026-05-24T00:00:00Z")
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {
        "high_priority_count": 2,
        "oldest_assignment_age_days": 14,
        "overdue_count": 1,
        "total_assignments": 3,
        "unassigned_count": 1,
    }
    assert parsed["counts_by_reviewer"] == {"alex": 1, "mika": 1, "unassigned": 1}
    assert parsed["counts_by_status"] == {"assigned": 2, "done": 1}
    assert [row["assignment_id"] for row in parsed["overdue_assignments"]] == ["r2"]
    assert output == review_assignment_queue_to_json(payload, as_of="2026-05-24T00:00:00Z")


def test_review_assignment_queue_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(review_assignment_queue_to_json({"review_assignments": [{}]}))

    assert parsed["assignments"][0] == {
        "age_days": None,
        "assigned_at": None,
        "assignment_id": "assignment-1",
        "due_at": None,
        "high_priority": False,
        "idea_id": None,
        "metadata": {},
        "overdue": False,
        "priority": "normal",
        "reviewer": "unassigned",
        "status": "assigned",
    }
    assert parsed["summary"]["unassigned_count"] == 1
