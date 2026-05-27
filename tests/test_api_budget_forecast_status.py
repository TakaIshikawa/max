from __future__ import annotations

import json

from max.api.budget_forecast_status import budget_forecast_status_to_json


def test_budget_forecast_status_marks_overrun_risk_and_sums_budget() -> None:
    report = json.loads(
        budget_forecast_status_to_json(
            {
                "budgets": [
                    {"profile": "p", "provider": "a", "spent_usd": 40, "budget_usd": 100, "projected_spend_usd": 120, "remaining_days": 5, "forecast_window_days": 30},
                    {"profile": "p", "provider": "b", "spent_usd": 3, "budget_usd": 0, "projected_spend_usd": 0, "remaining_days": 1, "forecast_window_days": 30},
                ]
            }
        )
    )

    assert report["rows"][0]["overrun_risk"] is True
    assert report["rows"][0]["spend_ratio"] == 0.4
    assert report["rows"][1]["spend_ratio"] == 1.0
    assert report["summary"]["total_spent_usd"] == 43.0
    assert report["summary"]["total_budget_usd"] == 100.0
    assert report["summary"]["projected_overrun_usd"] == 20.0
    assert report["summary"]["at_risk_count"] == 1
