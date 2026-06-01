from __future__ import annotations

import json

from max.api import pipeline_run_sla_status_to_json


def test_pipeline_run_sla_status_reports_breaches_and_worst_runs() -> None:
    rendered = json.loads(pipeline_run_sla_status_to_json({"duration_sla_seconds": 100, "runs": [{"run_id": "r1", "profile": "p1", "duration_seconds": 150, "failed_or_missing_stages": ["publish"]}, {"run_id": "r2", "profile": "p2", "status": "completed", "duration_seconds": 20}]}))

    assert rendered["schema_version"] == "max.api.pipeline_run_sla_status.v1"
    assert rendered["kind"] == "max.api.pipeline_run_sla_status"
    assert rendered["total_runs"] == 2
    assert rendered["breached_runs"] == 1
    assert rendered["missed_stage_counts"] == {"publish": 1}
    assert rendered["worst_runs"][0]["run_id"] == "r1"
    assert rendered["overall_status"] == "warning"
