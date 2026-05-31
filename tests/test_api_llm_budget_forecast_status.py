from __future__ import annotations

import json

from max.api.llm_budget_forecast_status import llm_budget_forecast_status_to_json


def test_llm_budget_forecast_status_under_budget() -> None:
    parsed = json.loads(llm_budget_forecast_status_to_json({"budget_usd": 100, "current_spend_usd": 20, "daily_burn_rate_usd": 5, "forecast_window_days": 7}))

    assert parsed["summary"]["status"] == "healthy"
    assert parsed["forecast"]["projected_exhaustion_days"] == 16.0


def test_llm_budget_forecast_status_near_exhaustion() -> None:
    parsed = json.loads(llm_budget_forecast_status_to_json({"budget_usd": 100, "current_spend_usd": 80, "daily_burn_rate_usd": 5, "forecast_window_days": 7}))

    assert parsed["forecast"]["severity"] == "warning"


def test_llm_budget_forecast_status_exhausted() -> None:
    parsed = json.loads(llm_budget_forecast_status_to_json({"budget_usd": 100, "current_spend_usd": 101, "daily_burn_rate_usd": 0}))

    assert parsed["summary"]["status"] == "exhausted"
    assert parsed["forecast"]["projected_exhaustion_days"] is None


def test_llm_budget_forecast_status_zero_budget_is_stable() -> None:
    parsed = json.loads(llm_budget_forecast_status_to_json({"budget_usd": 0, "current_spend_usd": 0}))

    assert parsed["summary"]["status"] == "no_budget"


def test_llm_budget_forecast_status_rounds_and_keeps_reserved_separate() -> None:
    parsed = json.loads(llm_budget_forecast_status_to_json({"budget_usd": 10.555, "current_spend_usd": 1.111, "reserved_budget_usd": 2.222, "daily_burn_rate_usd": 1.111}))

    assert parsed["summary"]["current_spend_usd"] == 1.11
    assert parsed["summary"]["reserved_budget_usd"] == 2.22
    assert parsed["summary"]["remaining_budget_usd"] == 7.22
