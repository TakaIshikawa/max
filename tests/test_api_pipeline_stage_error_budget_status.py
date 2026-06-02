from __future__ import annotations

import json

from max.api import pipeline_stage_error_budget_status_to_json


def test_pipeline_stage_error_budget_handles_zero_runs_and_sorts_exceeded() -> None:
    report = json.loads(pipeline_stage_error_budget_status_to_json({"stages": [{"stage": "ok", "failures": 0, "total_runs": 0, "allowed_failure_rate": 0.1}, {"stage": "bad", "failures": 2, "total_runs": 10, "allowed_failure_rate": 0.1}, {"stage": "warn", "failures": 0, "total_runs": 10, "allowed_failure_rate": 0.1, "recent_failures": 1}]}))

    assert report["stages"][0]["stage"] == "bad"
    assert report["stages"][0]["failure_rate"] == 0.2
    assert {row["stage"]: row["failure_rate"] for row in report["stages"]}["ok"] == 0.0
