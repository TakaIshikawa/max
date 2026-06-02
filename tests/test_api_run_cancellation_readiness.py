from __future__ import annotations

import json

from max.api.run_cancellation_readiness import run_cancellation_readiness_to_json


def test_run_cancellation_readiness_normalizes_sections_and_sorts_blocking_stages() -> None:
    parsed = json.loads(
        run_cancellation_readiness_to_json(
            {
                "run": {"id": "run-1", "status": "running"},
                "stages": [
                    {"name": "publish", "can_cancel": True},
                    {"name": "ingest", "blocked_reason": "external write"},
                    {"name": "score", "draining": True},
                ],
                "workers": [{"id": "w2", "stage": "ingest", "blocked_reason": "flush in progress"}],
                "cleanup_tasks": [{"id": "c1", "stage": "publish", "status": "pending"}],
                "cancellation_requests": [{"id": "r1", "requested_by": "ops"}],
            }
        )
    )

    assert parsed["schema_version"] == "max.api.run_cancellation_readiness.v1"
    assert parsed["run_summary"]["can_cancel_cleanly"] is False
    assert [row["stage"] for row in parsed["stage_readiness"]] == ["ingest", "score", "publish"]
    assert parsed["blocking_workers"][0]["worker_id"] == "w2"
    assert parsed["pending_cleanup_tasks"][0]["task_id"] == "c1"
    assert parsed["cancellation_requests"][0]["request_id"] == "r1"


def test_run_cancellation_readiness_empty_payload() -> None:
    parsed = json.loads(run_cancellation_readiness_to_json({}))

    assert parsed["run_summary"]["status"] == "unknown"
    assert parsed["stage_readiness"] == []
    assert parsed["blocking_workers"] == []
