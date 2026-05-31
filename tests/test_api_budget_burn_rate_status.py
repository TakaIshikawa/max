from __future__ import annotations

import json

from max.api import budget_burn_rate_status_to_json


def test_budget_burn_rate_status_flags_projected_exhaustion_and_totals() -> None:
    report = json.loads(budget_burn_rate_status_to_json({"stages": [{"stage": "synthesis", "planned_tokens": 100, "actual_tokens": 70, "planned_cost_usd": 10, "actual_cost_usd": 3, "run_progress_percent": 50}, {"stage": "eval", "planned_tokens": 100, "actual_tokens": 40, "run_progress_percent": 50}]}))

    assert report["stages"][0]["stage"] == "synthesis"
    assert report["stages"][0]["severity"] == "critical"
    assert report["summary"]["highest_severity"] == "critical"
    assert report["summary"]["total_projected_overrun"] == 40.0


def test_budget_burn_rate_status_empty_input_is_ok() -> None:
    report = json.loads(budget_burn_rate_status_to_json({}))

    assert report["summary"]["highest_severity"] == "ok"
    assert report["summary"]["total_projected_overrun"] == 0
    assert report["stages"] == []
