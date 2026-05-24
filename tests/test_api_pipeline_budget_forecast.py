from __future__ import annotations

import json

from max.api.pipeline_budget_forecast import pipeline_budget_forecast_to_json


def test_pipeline_budget_forecast_clamps_negative_inputs_and_rounds_ratios() -> None:
    parsed = json.loads(pipeline_budget_forecast_to_json({"remaining_tokens": 100, "remaining_cost": 10, "stages": [{"stage": "fetch", "tokens": -1, "cost": "bad"}, {"stage": "ideate", "tokens": 33, "cost": 1}]}))

    assert parsed["stages"][0]["stage"] == "ideate"
    assert parsed["stages"][0]["token_utilization_ratio"] == 0.33
    assert parsed["projected_totals"]["projected_tokens"] == 33
    assert parsed["summary"]["status"] == "safe"


def test_pipeline_budget_forecast_marks_stage_overrun() -> None:
    parsed = json.loads(pipeline_budget_forecast_to_json({"remaining_tokens": 100, "remaining_cost": 5, "stages": [{"stage": "evaluate", "projected_tokens": 101, "projected_cost": 1}]}))

    assert parsed["summary"]["status"] == "overrun"
    assert parsed["stage_risks"][0]["status"] == "overrun"
    assert parsed["reservation_gap"]["tokens"] == 1


def test_pipeline_budget_forecast_watch_threshold() -> None:
    parsed = json.loads(pipeline_budget_forecast_to_json({"remaining_tokens": 100, "remaining_cost": 10, "stages": [{"stage": "spec", "tokens": 80, "cost": 2}]}))

    assert parsed["summary"]["status"] == "watch"
