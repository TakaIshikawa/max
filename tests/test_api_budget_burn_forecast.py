from __future__ import annotations

import json

from max.api.budget_burn_forecast import (
    KIND,
    SCHEMA_VERSION,
    budget_burn_forecast_to_json,
)


def test_budget_burn_forecast_to_json_projects_usage_and_risk() -> None:
    payload = {
        "schema_version": "max.budget_burn_forecast.v1",
        "kind": "max.budget_burn_forecast",
        "current_usage": {"tokens_used": 900, "cost_usd": 4.2},
        "limits": {"token_limit": 1000, "cost_limit_usd": 5.0},
        "remaining_stages": [
            {"stage": "publish", "estimated_tokens": 50, "estimated_cost_usd": 0.3},
            {"stage": "evaluate", "estimated_tokens": "75", "estimated_cost_usd": "0.8"},
        ],
    }

    output = budget_burn_forecast_to_json(payload)
    parsed = json.loads(output)

    assert parsed["schema_version"] == SCHEMA_VERSION
    assert parsed["kind"] == KIND
    assert parsed["summary"] == {
        "overrun_risk": "overrun",
        "projected_total_cost_usd": 5.3,
        "projected_total_tokens": 1025,
        "remaining_cost_budget_usd": -0.3,
        "remaining_token_budget": -25,
        "unknown_stage_count": 0,
    }
    assert [row["stage"] for row in parsed["remaining_stages"]] == ["evaluate", "publish"]
    assert output == budget_burn_forecast_to_json(payload)


def test_budget_burn_forecast_to_json_records_unknown_stage_estimates() -> None:
    parsed = json.loads(
        budget_burn_forecast_to_json(
            {
                "tokens_used": 10,
                "cost_usd": 0.5,
                "token_limit": 100,
                "cost_limit_usd": 10,
                "stage_estimates": [{"stage": "publish"}],
            }
        )
    )

    assert parsed["remaining_stages"][0]["estimate_status"] == "unknown"
    assert parsed["summary"]["unknown_stage_count"] == 1
    assert parsed["summary"]["overrun_risk"] == "watch"
