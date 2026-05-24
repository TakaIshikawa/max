from __future__ import annotations

import json

from max.api.tact_publish_readiness import KIND, SCHEMA_VERSION, tact_publish_readiness_to_json


def test_tact_publish_readiness_derives_ready_and_destination_rollups() -> None:
    payload = {
        "generated_specs": [
            {"spec_id": "s2", "destination": "jira", "validation_status": "failed", "failure_reasons": ["schema"], "publisher_configured": True},
            {"spec_id": "s1", "destination": "github", "validation_status": "ready", "destination_ready": True},
            {"spec_id": "s3", "destination": "jira", "validation_status": "ready", "destination_ready": False, "missing_evidence": ["e1"]},
        ]
    }

    parsed = json.loads(tact_publish_readiness_to_json(payload))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {"blocked_count": 2, "ready_count": 1, "total_count": 3}
    assert [row["spec_id"] for row in parsed["specs"]] == ["s1", "s2", "s3"]
    assert parsed["destinations"] == [
        {"configured_count": 1, "destination": "github", "ready_count": 1, "unconfigured_count": 0},
        {"configured_count": 1, "destination": "jira", "ready_count": 0, "unconfigured_count": 1},
    ]
    assert parsed["validation_failures"] == [{"reasons": ["schema"], "spec_id": "s2"}]
    assert parsed["missing_evidence"] == [{"evidence_ids": ["e1"], "spec_id": "s3"}]
    assert [row["id"] for row in parsed["next_actions"]] == ["fix-s2", "fix-s3"]
    assert tact_publish_readiness_to_json(payload) == tact_publish_readiness_to_json({"generated_specs": list(reversed(payload["generated_specs"]))})


def test_tact_publish_readiness_honors_explicit_sections() -> None:
    parsed = json.loads(
        tact_publish_readiness_to_json(
            {
                "specs": [{}],
                "summary": {"ready_count": 9},
                "destinations": [{"destination": "manual", "configured_count": 1}],
                "validation_failures": [{"spec_id": "s"}],
                "missing_evidence": [{"spec_id": "s", "evidence_ids": ["e"]}],
                "dry_run_results": [{"spec_id": "s", "destination": "manual", "status": "ok"}],
                "next_actions": [{"id": "manual"}],
            }
        )
    )

    assert parsed["summary"]["ready_count"] == 9
    assert parsed["destinations"][0]["destination"] == "manual"
    assert parsed["validation_failures"][0]["spec_id"] == "s"
    assert parsed["missing_evidence"][0]["evidence_ids"] == ["e"]
    assert parsed["dry_run_results"][0]["status"] == "ok"
    assert parsed["next_actions"][0]["id"] == "manual"
