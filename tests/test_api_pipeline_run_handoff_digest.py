from __future__ import annotations

import json

from max.api.pipeline_run_handoff_digest import (
    KIND,
    SCHEMA_VERSION,
    pipeline_run_handoff_digest_to_json,
)


def test_pipeline_run_handoff_digest_to_json_normalizes_sections() -> None:
    payload = {
        "schema_version": "max.pipeline_run_handoff_digest.v1",
        "kind": "max.pipeline_run_handoff_digest",
        "run": {
            "id": "run-001",
            "status": "completed",
            "started_at": "2026-05-20T00:00:00",
            "completed_at": "2026-05-20T00:10:00",
            "profile": "nightly",
            "domain": "payments",
        },
        "summary": {"idea_count": 3, "warning_count": 1, "next_action_count": 2},
        "stage_counts": {"ideas_generated": 3, "signals_fetched": 10},
        "budget": {
            "model": "gpt-test",
            "total_tokens": 1200,
            "estimated_cost_usd": 0.42,
            "stages": [
                {"stage": "evaluate", "input_tokens": 500, "output_tokens": 50, "total_tokens": 550}
            ],
        },
        "warnings": ["Publication retry remains open"],
        "next_actions": [{"action": "Retry publication", "owner": "ops", "due_date": "2026-05-21"}],
        "owners": [{"owner": "ops", "role": "operator", "responsibilities": ["publication retry"]}],
    }

    output = pipeline_run_handoff_digest_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["run_summary"]["run_id"] == "run-001"
    assert parsed["run_summary"]["budget"]["total_tokens"] == 1200
    assert [row["stage"] for row in parsed["stage_statuses"]] == [
        "evaluate",
        "ideas_generated",
        "signals_fetched",
    ]
    assert parsed["blockers"][0]["message"] == "Publication retry remains open"
    assert parsed["next_actions"][0]["owner"] == "ops"
    assert parsed["owners"][0]["role"] == "operator"
    assert parsed["metadata"]["source_kind"] == "max.pipeline_run_handoff_digest"
    assert output == pipeline_run_handoff_digest_to_json(payload)


def test_pipeline_run_handoff_digest_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(pipeline_run_handoff_digest_to_json({}))

    assert parsed["run_summary"]["run_id"] is None
    assert parsed["run_summary"]["budget"] == {
        "estimated_cost_usd": 0.0,
        "model": None,
        "total_tokens": 0,
    }
    assert parsed["stage_statuses"] == []
    assert parsed["blockers"] == []
    assert parsed["next_actions"] == []
    assert parsed["owners"] == []
    assert parsed["metadata"]["source_kind"] is None
