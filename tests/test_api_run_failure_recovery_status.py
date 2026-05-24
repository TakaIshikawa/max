from __future__ import annotations

import json

from max.api.run_failure_recovery_status import run_failure_recovery_status_to_json


def test_run_failure_recovery_status_classifies_failures() -> None:
    parsed = json.loads(
        run_failure_recovery_status_to_json(
            {
                "runs": [
                    {"id": "resume", "stage": "publish", "checkpoint": "after-build"},
                    {"id": "retry", "stage": "fetch", "retryable": True},
                    {"id": "blocked", "stage": "score", "dependencies": ["index"]},
                    {"id": "dead", "stage": "export", "fatal": True, "lost_artifacts": ["a", "b"]},
                ]
            }
        )
    )

    assert parsed["summary"]["resumable_count"] == 1
    assert parsed["summary"]["retryable_count"] == 1
    assert parsed["summary"]["blocked_count"] == 1
    assert parsed["summary"]["terminal_count"] == 1
    assert [row["run_id"] for row in parsed["runs"]][0] == "dead"


def test_run_failure_recovery_status_checkpoint_aliases_and_actions() -> None:
    parsed = json.loads(run_failure_recovery_status_to_json({"failures": [{"run_id": "r1", "failed_stage": "s", "resume_from": "cp", "owner": "ops"}]}, as_of="2026-05-21T00:00:00Z"))

    assert parsed["runs"][0]["recovery_status"] == "resumable"
    assert parsed["runs"][0]["retry_eligible"] is False
    assert parsed["recovery_actions"][0]["checkpoint"] == "cp"
    assert parsed["metadata"]["as_of"] == "2026-05-21T00:00:00Z"


def test_run_failure_recovery_status_missing_artifact_inventory_defaults_to_zero() -> None:
    parsed = json.loads(run_failure_recovery_status_to_json({"runs": [{"id": "r", "retryable": True, "missing_artifacts": "bad"}]}))

    assert parsed["runs"][0]["lost_artifact_count"] == 0
    assert parsed["runs"][0]["severity"] == "low"
