from __future__ import annotations

import json

from max.api.pipeline_stage_sla_status import pipeline_stage_sla_status_to_json


def test_pipeline_stage_sla_status_derives_sla_states() -> None:
    parsed = json.loads(
        pipeline_stage_sla_status_to_json(
            {
                "stages": [
                    {"run_id": "r1", "stage": "extract", "duration_seconds": 10, "sla_seconds": 20},
                    {"run_id": "r1", "stage": "transform", "duration_seconds": 17, "sla_seconds": 20},
                    {"run_id": "r2", "stage": "load", "duration_seconds": 25, "sla_seconds": 20},
                    {"run_id": "r0", "stage": "publish", "state": "stalled", "duration_seconds": -1, "queue_seconds": "bad"},
                ]
            }
        )
    )

    assert [row["status"] for row in parsed["stages"]] == ["stalled", "breached", "warning", "healthy"]
    assert parsed["stages"][0]["duration_seconds"] == 0.0
    assert parsed["stages"][0]["queue_seconds"] == 0.0
    assert parsed["summary"]["max_duration_seconds"] == 25.0
    assert parsed["summary"]["stalled_count"] == 1
    assert parsed["breached_stages"][1]["stage"] == "load"


def test_pipeline_stage_sla_status_aliases_totals_and_metadata() -> None:
    parsed = json.loads(pipeline_stage_sla_status_to_json({"pipeline_stages": [{"run": "r", "name": "n", "duration": "8", "sla": "10"}]}, as_of="now"))

    assert parsed["stages"][0]["status"] == "warning"
    assert parsed["run_totals"][0]["run_id"] == "r"
    assert parsed["metadata"]["as_of"] == "now"
