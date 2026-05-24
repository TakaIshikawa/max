from __future__ import annotations

import json

from max.api.run_resume_checkpoint_status import run_resume_checkpoint_status_to_json


def test_run_resume_checkpoint_status_derives_resume_and_missing_artifacts() -> None:
    parsed = json.loads(
        run_resume_checkpoint_status_to_json(
            {
                "checkpoints": [
                    {"run_id": "r1", "stage": "a", "checkpoint_id": "done", "completed_at": "now", "artifact_uri": "s3://x"},
                    {"run_id": "r1", "stage": "b", "checkpoint_id": "missing", "completed_at": "now"},
                    {"run_id": "r2", "stage": "a", "checkpoint_id": "resume", "resumable": "true"},
                    {"run_id": "r2", "stage": "b", "checkpoint_id": "fail", "error": "boom"},
                ]
            }
        )
    )

    assert parsed["schema_version"] == "max.api.run_resume_checkpoint_status.v1"
    assert [row["checkpoint_id"] for row in parsed["checkpoints"]] == ["fail", "missing", "resume", "done"]
    assert parsed["summary"]["checkpoint_count"] == 4
    assert parsed["summary"]["resumable_count"] == 1
    assert parsed["summary"]["failed_count"] == 1
    assert parsed["summary"]["missing_artifact_count"] == 1
    assert parsed["summary"]["run_count"] == 2


def test_run_resume_checkpoint_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(run_resume_checkpoint_status_to_json({"run_checkpoints": [{"run_id": "r", "stage": "s", "id": "c"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["resume_candidates"][0]["checkpoint_id"] == "c"
    assert parsed["run_totals"][0]["run_id"] == "r"
    assert parsed["stage_totals"][0]["stage"] == "s"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"
