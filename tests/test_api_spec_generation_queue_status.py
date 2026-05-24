from __future__ import annotations

import json

from max.api.spec_generation_queue_status import KIND, SCHEMA_VERSION, spec_generation_queue_status_to_json


def test_spec_generation_queue_status_derives_status_sorting_and_age_buckets() -> None:
    payload = {
        "approved_ideas": [
            {"idea_id": "i2", "status": "blocked", "template": "prd", "owner": "bea", "approved_at": "2026-05-01T00:00:00Z", "blocked_reason": "missing evidence"},
            {"idea_id": "i1", "status": "ready", "template_id": "brief", "owner": "ada", "approved_at": "2026-05-20T00:00:00Z"},
            {"idea_id": "i3", "status": "generated", "template": "prd", "approved_at": "2026-04-01T00:00:00Z"},
        ]
    }

    parsed = json.loads(spec_generation_queue_status_to_json(payload, as_of="2026-05-21T00:00:00Z"))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"blocked_count": 1, "generated_count": 1, "ready_count": 1, "total_count": 3}
    assert [row["idea_id"] for row in parsed["queue_items"]] == ["i1", "i2", "i3"]
    assert parsed["template_mix"] == [{"count": 1, "template": "brief"}, {"count": 2, "template": "prd"}]
    assert parsed["blocked_items"] == [{"blocker_reasons": ["missing evidence"], "idea_id": "i2", "owner": "bea"}]
    assert parsed["age_buckets"]["0_1d"] == 1
    assert parsed["age_buckets"]["8_30d"] == 1
    assert parsed["age_buckets"]["over_30d"] == 1
    assert parsed["next_actions"][0]["id"] == "unblock-i2"
    assert spec_generation_queue_status_to_json(payload, as_of="2026-05-21T00:00:00Z") == spec_generation_queue_status_to_json({"approved_ideas": list(reversed(payload["approved_ideas"]))}, as_of="2026-05-21T00:00:00Z")


def test_spec_generation_queue_status_honors_explicit_sections() -> None:
    parsed = json.loads(
        spec_generation_queue_status_to_json(
            {
                "queue_items": [{}],
                "summary": {"ready_count": 7},
                "template_mix": [{"template": "custom", "count": 2}],
                "blocked_items": [{"idea_id": "i"}],
                "owner_hints": [{"owner": "owner", "idea_ids": ["i"]}],
                "next_actions": [{"id": "manual"}],
            }
        )
    )

    assert parsed["summary"]["ready_count"] == 7
    assert parsed["template_mix"][0]["template"] == "custom"
    assert parsed["blocked_items"][0]["idea_id"] == "i"
    assert parsed["owner_hints"][0]["owner"] == "owner"
    assert parsed["next_actions"][0]["id"] == "manual"
