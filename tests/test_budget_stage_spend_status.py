from __future__ import annotations

import json

from max.api.budget_stage_spend_status import budget_stage_spend_status_to_json


def test_budget_stage_spend_status_calculates_under_budget() -> None:
    report = json.loads(budget_stage_spend_status_to_json({"stages": [{"stage": "fetch", "allocated_amount": 100, "actual_spend": 50}]}))

    assert report["stages"][0]["percent_used"] == 0.5
    assert report["stages"][0]["variance"] == 50
    assert report["stages"][0]["status"] == "healthy"


def test_budget_stage_spend_status_flags_warning_and_over_budget() -> None:
    report = json.loads(budget_stage_spend_status_to_json({"stages": [{"stage": "warn", "allocated": 100, "spend": 80}, {"stage": "over", "allocated": 100, "spend": 120}]}))

    assert [row["status"] for row in report["stages"]] == ["critical", "warning"]
    assert report["summary"]["status"] == "critical"


def test_budget_stage_spend_status_handles_zero_allocation() -> None:
    report = json.loads(budget_stage_spend_status_to_json({"stages": [{"stage": "free", "allocated": 0, "spend": 0}, {"stage": "leak", "allocated": 0, "spend": 1}]}))

    assert report["stages"][0]["stage"] == "leak"
    assert report["stages"][0]["status"] == "critical"
    assert report["stages"][1]["percent_used"] == 0.0
