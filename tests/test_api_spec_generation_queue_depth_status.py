from __future__ import annotations

import json

from max.api import spec_generation_queue_depth_status_to_json


def test_spec_generation_queue_depth_status_reports_blocked_ratio_and_reasons() -> None:
    report = json.loads(spec_generation_queue_depth_status_to_json({"jobs": [{"id": "a", "status": "blocked", "queued_age_seconds": 50, "reason": "quota"}, {"id": "b", "status": "failed", "reason": "quota"}, {"id": "c", "status": "pending", "queued_age_seconds": 20}]}))

    assert report["summary"]["status"] == "warning"
    assert report["summary"]["blocked_ratio"] == 0.3333
    assert report["summary"]["oldest_queued_age_seconds"] == 50
    assert report["bottleneck_reasons"] == [{"reason": "quota", "count": 2}]


def test_spec_generation_queue_depth_status_empty_queue_is_healthy() -> None:
    report = json.loads(spec_generation_queue_depth_status_to_json({}))

    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["job_count"] == 0
