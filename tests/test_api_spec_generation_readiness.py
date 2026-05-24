from __future__ import annotations

import json

from max.api.spec_generation_readiness import spec_generation_readiness_to_json


def test_spec_generation_readiness_classifies_ready_blocked_and_review() -> None:
    parsed = json.loads(
        spec_generation_readiness_to_json(
            {
                "buildable_units": [
                    {"id": "u3", "name": "Review", "evidence_count": 0, "recommendation": "review"},
                    {"id": "u1", "name": "Ready", "evidence_count": 2, "recommendation": "build"},
                    {"id": "u2", "name": "Blocked", "evidence_count": 3, "missing_fields": ["Owner", "data contract"], "owner": "pm"},
                ]
            }
        )
    )

    assert [row["unit_id"] for row in parsed["ready_units"]] == ["u1"]
    assert [row["unit_id"] for row in parsed["blocked_units"]] == ["u3", "u2"]
    assert parsed["readiness_buckets"] == {"blocked": 1, "needs_review": 1, "ready": 1}


def test_spec_generation_readiness_defaults_and_missing_input_reasons() -> None:
    parsed = json.loads(spec_generation_readiness_to_json({"units": [{}]}))

    assert parsed["blocked_units"][0]["unit_id"] == "U1"
    assert parsed["blocked_units"][0]["readiness"] == "needs_review"
    assert parsed["blocked_units"][0]["missing_inputs"] == []


def test_spec_generation_readiness_owner_hints_next_actions_and_metadata() -> None:
    parsed = json.loads(
        spec_generation_readiness_to_json(
            {"schema_version": "source.v1", "kind": "source.kind", "units": [{"id": "u1", "status": "blocked", "missing": "Legal Approval", "owner": "legal"}]},
            as_of="2026-05-21T00:00:00Z",
        )
    )

    assert parsed["owner_hints"] == [{"blocked_count": 1, "owner": "legal", "unit_ids": ["u1"]}]
    assert parsed["next_actions"][0]["missing_inputs"] == ["legal_approval"]
    assert set(parsed) == {"schema_version", "kind", "summary", "ready_units", "blocked_units", "readiness_buckets", "owner_hints", "next_actions", "metadata"}
    assert parsed["metadata"]["source_schema_version"] == "source.v1"
