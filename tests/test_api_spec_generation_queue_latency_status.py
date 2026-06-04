from __future__ import annotations

import json

from max.api.spec_generation_queue_latency_status import spec_generation_queue_latency_status_to_json


def test_spec_generation_queue_latency_status_counts_active_and_history() -> None:
    report = json.loads(
        spec_generation_queue_latency_status_to_json(
            [
                {"job_id": "q", "status": "queued", "queued_at": "2026-01-01T22:00:00Z"},
                {"job_id": "r", "status": "running", "queued_at": "2026-01-01T23:30:00Z"},
                {"job_id": "c", "status": "completed", "queued_at": "2026-01-01T20:00:00Z", "started_at": "2026-01-01T20:45:00Z"},
                {"job_id": "f", "status": "failed"},
            ],
            now="2026-01-02T00:00:00Z",
        )
    )

    assert report["summary"]["active_backlog_count"] == 2
    assert report["summary"]["oldest_queued_age_minutes"] == 120.0
    assert report["summary"]["p95_queue_latency_minutes"] == 45.0
    assert report["status"] == "critical"

