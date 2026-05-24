from __future__ import annotations

import json

from max.api.pipeline_stage_latency import KIND, SCHEMA_VERSION, pipeline_stage_latency_to_json


def test_pipeline_stage_latency_derives_duration_and_bottlenecks() -> None:
    payload = {
        "run": {"id": "run-1", "status": "completed"},
        "stage_timings": [
            {"stage_id": "s2", "stage_name": "publish", "duration_ms": 300, "queue_ms": 10, "retry_count": 1},
            {"stage_id": "s1", "stage_name": "ingest", "started_at": "2026-05-21T00:00:00Z", "completed_at": "2026-05-21T00:00:02Z", "slow_threshold_ms": 1000},
        ],
    }

    parsed = json.loads(pipeline_stage_latency_to_json(payload))

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["run_summary"]["total_duration_ms"] == 2300
    assert [row["stage_name"] for row in parsed["stages"]] == ["ingest", "publish"]
    assert parsed["stages"][0]["duration_ms"] == 2000
    assert [row["stage_name"] for row in parsed["bottlenecks"]] == ["ingest", "publish"]
    assert parsed["retry_latency"] == {"duration_ms": 300, "retried_stage_count": 1, "total_retry_count": 1}
    assert parsed["threshold_violations"] == [{"duration_ms": 2000, "slow_threshold_ms": 1000, "stage_id": "s1", "stage_name": "ingest"}]


def test_pipeline_stage_latency_explicit_duration_takes_precedence() -> None:
    parsed = json.loads(
        pipeline_stage_latency_to_json(
            {
                "stages": [
                    {
                        "stage_id": "s",
                        "stage_name": "same",
                        "started_at": "2026-05-21T00:00:00Z",
                        "completed_at": "2026-05-21T00:01:00Z",
                        "duration_ms": 5,
                    }
                ],
                "bottlenecks": [{"stage_id": "b", "stage_name": "manual", "duration_ms": 9}],
            }
        )
    )

    assert parsed["stages"][0]["duration_ms"] == 5
    assert parsed["bottlenecks"][0]["stage_name"] == "manual"
