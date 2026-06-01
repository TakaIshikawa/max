from __future__ import annotations

import json

from max.api import llm_cost_projection_status_to_json


def test_llm_cost_projection_status_under_budget() -> None:
    report = json.loads(llm_cost_projection_status_to_json({"current_spend": 50, "reserved_budget": 100, "projected_spend": 90}))
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["remaining_budget"] == 50


def test_llm_cost_projection_status_warning() -> None:
    report = json.loads(llm_cost_projection_status_to_json({"current_spend": 80, "reserved_budget": 100, "projected_spend": 105}))
    assert report["summary"]["status"] == "warning"
    assert report["summary"]["projected_overrun"] == 5


def test_llm_cost_projection_status_critical_and_sorts_drivers() -> None:
    report = json.loads(llm_cost_projection_status_to_json({"reserved_budget": 100, "projected_spend": 130, "critical_projected_overrun": 0.2, "max_drivers": 2, "drivers": [{"model": "small", "projected_cost": 4}, {"model": "large", "projected_cost": 20}, {"model": "mid", "projected_cost": 10}]}))
    assert report["summary"]["status"] == "critical"
    assert [row["model"] for row in report["top_cost_drivers"]] == ["large", "mid"]


def test_llm_cost_projection_status_no_budget_configured() -> None:
    report = json.loads(llm_cost_projection_status_to_json({"projected_spend": 500}))
    assert report["summary"]["status"] == "healthy"
    assert report["summary"]["projected_budget_utilization"] == 0.0

