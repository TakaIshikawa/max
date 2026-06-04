from __future__ import annotations

import json

from max.api import runtime_artifact_write_failure_status_to_json


def test_no_failures_return_empty_summary() -> None:
    report = json.loads(runtime_artifact_write_failure_status_to_json({}))
    assert report["summary"]["failure_group_count"] == 0


def test_retryable_failures_are_warning() -> None:
    report = json.loads(runtime_artifact_write_failure_status_to_json({"failures": [{"artifact_type": "json", "run_id": "r1", "reason": "timeout", "retryable": True}]}))
    assert report["failure_rows"][0]["retryable_failure_count"] == 1
    assert report["failure_rows"][0]["status"] == "warning"


def test_terminal_failures_are_critical() -> None:
    report = json.loads(runtime_artifact_write_failure_status_to_json({"rows": [{"artifact_type": "json", "run_id": "r1", "reason": "permission", "retryable": False}]}))
    assert report["failure_rows"][0]["status"] == "critical"


def test_stale_repeated_failures_stay_warning() -> None:
    report = json.loads(runtime_artifact_write_failure_status_to_json({"items": [{"artifact_type": "json", "run_id": "r1", "reason": "timeout", "retryable": True}, {"artifact_type": "json", "run_id": "r1", "reason": "timeout", "retryable": True}, {"artifact_type": "json", "run_id": "r1", "reason": "timeout", "retryable": True}]}))
    assert report["failure_rows"][0]["retryable_failure_count"] == 3


def test_malformed_timestamps_are_deterministic() -> None:
    report = json.loads(runtime_artifact_write_failure_status_to_json({"items": [{"artifact_type": "json", "timestamp": {"bad": "shape"}, "retryable": True}]}))
    assert report["failure_rows"][0]["latest_failure_at"] is not None
