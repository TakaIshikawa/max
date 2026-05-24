from __future__ import annotations

import json

from max.api.idea_review_queue_status import KIND, SCHEMA_VERSION, idea_review_queue_status_to_json


def test_idea_review_queue_status_derives_sections_and_age_buckets() -> None:
    payload = {
        "schema_version": "max.idea_review_queue_status.v1",
        "kind": "max.idea_review_queue_status",
        "ideas": [
            {"idea_id": "idea-b", "status": "escalated", "reviewer": "bea", "created_at": "2026-05-01T00:00:00Z", "recommendation": "hold", "escalation_reasons": ["policy"]},
            {"idea_id": "idea-a", "status": "pending", "reviewer": "ada", "submitted_at": "2026-05-20T00:00:00Z", "recommendation": "approve"},
            {"idea_id": "idea-c", "status": "reviewed", "reviewer": "ada", "created_at": "2026-04-01T00:00:00Z", "recommendation": "approve"},
        ],
    }

    parsed = json.loads(idea_review_queue_status_to_json(payload, as_of="2026-05-21T00:00:00Z"))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"escalated_count": 1, "pending_count": 1, "reviewed_count": 1, "total_count": 3}
    assert [row["idea_id"] for row in parsed["review_items"]] == ["idea-a", "idea-b", "idea-c"]
    assert parsed["reviewer_load"] == [
        {"escalated_count": 0, "idea_ids": ["idea-a", "idea-c"], "pending_count": 1, "reviewed_count": 1, "reviewer": "ada"},
        {"escalated_count": 1, "idea_ids": ["idea-b"], "pending_count": 0, "reviewed_count": 0, "reviewer": "bea"},
    ]
    assert parsed["recommendation_counts"] == {"approve": 2, "hold": 1}
    assert parsed["next_actions"] == [{"action": "Resolve escalated idea review", "idea_id": "idea-b", "id": "resolve-idea-b", "owner": "bea"}]
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
    reordered_payload = {**payload, "ideas": list(reversed(payload["ideas"]))}
    assert idea_review_queue_status_to_json(payload, as_of="2026-05-21T00:00:00Z") == idea_review_queue_status_to_json(reordered_payload, as_of="2026-05-21T00:00:00Z")


def test_idea_review_queue_status_honors_explicit_override_sections() -> None:
    parsed = json.loads(
        idea_review_queue_status_to_json(
            {
                "ideas": [{"idea_id": "idea-1"}],
                "summary": {"pending_count": 9},
                "reviewer_load": [{"reviewer": "zoe", "pending_count": 3, "idea_ids": ["idea-1"]}],
                "stale_items": [{"idea_id": "idea-1", "age_bucket": "over_30d"}],
                "recommendation_counts": {"approve": "4"},
                "next_actions": [{"id": "custom", "action": "Assign reviewer"}],
            }
        )
    )

    assert parsed["summary"]["pending_count"] == 9
    assert parsed["reviewer_load"][0]["reviewer"] == "zoe"
    assert parsed["stale_items"][0]["age_bucket"] == "over_30d"
    assert parsed["recommendation_counts"] == {"approve": 4}
    assert parsed["next_actions"][0]["id"] == "custom"
