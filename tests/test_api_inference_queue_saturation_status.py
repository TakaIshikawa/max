from __future__ import annotations

import json

from max.api import inference_queue_saturation_status_to_json


def test_inference_queue_saturation_status_derives_and_clamps_utilization() -> None:
    parsed = json.loads(inference_queue_saturation_status_to_json({"queues": [{"queue_name": "derive", "pending_jobs": 4, "running_jobs": 6, "capacity": 10}, {"queue_name": "clamp", "utilization": 2, "oldest_job_age_minutes": 5}]}))
    queues = {row["queue_name"]: row for row in parsed["queues"]}

    assert queues["derive"]["utilization"] == 1.0
    assert queues["clamp"]["utilization"] == 1.0
    assert parsed["summary"]["saturated_count"] == 2


def test_inference_queue_saturation_status_age_drives_severity() -> None:
    parsed = json.loads(inference_queue_saturation_status_to_json({"queue_metrics": [{"queue": "old", "oldest_age_minutes": 130}, {"queue": "fresh", "oldest_age_minutes": 0}]}))

    assert [row["status"] for row in parsed["queues"]] == ["critical", "low"]
    assert parsed["summary"]["max_oldest_job_age_minutes"] == 130
