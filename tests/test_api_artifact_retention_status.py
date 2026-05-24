from __future__ import annotations

import json

from max.api.artifact_retention_status import artifact_retention_status_to_json


def test_artifact_retention_status_orders_actionable_rows_and_counts() -> None:
    parsed = json.loads(
        artifact_retention_status_to_json(
            {
                "artifacts": [
                    {"id": "held", "run": "r2", "artifact_type": "log", "age": 999, "retention": 10, "legal_hold": "true"},
                    {"artifact_id": "near", "run_id": "r1", "type": "trace", "age_days": 9, "retention_days": 10},
                    {"artifact_id": "old", "run_id": "r0", "type": "trace", "age_days": 12, "retention_days": 10},
                    {"artifact_id": "keep", "run_id": "r1", "type": "log", "age_days": 1, "retention_days": 10},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.artifact_retention_status.v1"
    assert [row["artifact_id"] for row in parsed["artifacts"]] == ["old", "near", "keep", "held"]
    assert [row["status"] for row in parsed["artifacts"]] == ["expired", "nearing_expiry", "retained", "legal_hold"]
    assert parsed["summary"]["expired_count"] == 1
    assert parsed["summary"]["legal_hold_count"] == 1
    assert parsed["expired_artifacts"][0]["delete_after_days"] == 0
    assert parsed["type_totals"][1]["type"] == "trace"


def test_artifact_retention_status_clamps_malformed_values_and_empty_payload() -> None:
    parsed = json.loads(artifact_retention_status_to_json({"run_artifacts": [{"age": "-2", "retention": "bad"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["artifacts"][0]["age_days"] == 0
    assert parsed["artifacts"][0]["retention_days"] == 0
    assert parsed["artifacts"][0]["delete_after_days"] == 0
    assert parsed["artifacts"][0]["status"] == "retained"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
    assert json.loads(artifact_retention_status_to_json({}))["summary"]["artifact_count"] == 0
