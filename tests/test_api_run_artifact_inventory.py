from __future__ import annotations

import json

from max.api.run_artifact_inventory import (
    KIND,
    SCHEMA_VERSION,
    run_artifact_inventory_to_json,
)


def test_run_artifact_inventory_to_json_groups_and_sorts_artifacts() -> None:
    payload = {
        "schema_version": "max.run_artifact_inventory.v1",
        "kind": "max.run_artifact_inventory",
        "run": {"id": "run-001", "status": "completed", "profile": "nightly"},
        "artifacts": [
            {
                "id": "z-report",
                "stage": "publish",
                "type": "markdown",
                "uri": "s3://bucket/report.md",
                "created_at": "2026-05-20T00:03:00Z",
            },
            {
                "id": "a-signals",
                "stage": "ingest",
                "type": "json",
                "path": "/tmp/signals.json",
                "created_at": "2026-05-20T00:01:00Z",
            },
            {
                "id": "b-eval",
                "stage": "evaluate",
                "type": "json",
                "path": "/tmp/eval.json",
                "created_at": "2026-05-20T00:02:00Z",
            },
        ],
    }

    output = run_artifact_inventory_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["run_summary"]["run_id"] == "run-001"
    assert parsed["summary"] == {
        "latest_artifact_created_at": "2026-05-20T00:03:00Z",
        "missing_location_count": 0,
        "stage_count": 3,
        "total_artifacts": 3,
        "type_count": 2,
    }
    assert [row["artifact_id"] for row in parsed["artifacts"]] == ["b-eval", "a-signals", "z-report"]
    assert parsed["counts_by_stage"] == {"evaluate": 1, "ingest": 1, "publish": 1}
    assert parsed["counts_by_type"] == {"json": 2, "markdown": 1}
    assert parsed["artifacts_by_stage"][0] == {
        "artifact_ids": ["b-eval"],
        "count": 1,
        "name": "evaluate",
    }
    assert output == run_artifact_inventory_to_json(payload)


def test_run_artifact_inventory_to_json_handles_empty_artifacts() -> None:
    parsed = json.loads(run_artifact_inventory_to_json({"run_id": "run-empty", "artifacts": []}))

    assert parsed["run_summary"]["run_id"] == "run-empty"
    assert parsed["summary"]["total_artifacts"] == 0
    assert parsed["summary"]["latest_artifact_created_at"] is None
    assert parsed["artifacts"] == []
    assert parsed["counts_by_stage"] == {}
    assert parsed["counts_by_type"] == {}


def test_run_artifact_inventory_to_json_defaults_missing_optional_fields() -> None:
    parsed = json.loads(run_artifact_inventory_to_json({"artifact_records": [{}]}))

    assert parsed["artifacts"] == [
        {
            "artifact_id": "artifact-1",
            "created_at": None,
            "location": None,
            "metadata": {},
            "path": None,
            "stage": "unknown-stage",
            "type": "unknown-type",
            "uri": None,
        }
    ]
    assert parsed["summary"]["missing_location_count"] == 1
    assert parsed["counts_by_stage"] == {"unknown-stage": 1}
