from __future__ import annotations

import json

from max.api.llm_budget_burn_rate_status import llm_budget_burn_rate_status_to_json


def test_llm_budget_burn_rate_status_projects_at_risk_rows() -> None:
    report = json.loads(
        llm_budget_burn_rate_status_to_json(
            {
                "budgets": [
                    {"provider": "openai", "model": "m", "profile": "p", "tokens_used": 60, "token_budget": 100, "cost_usd": 2, "cost_budget_usd": 10, "elapsed_window_minutes": 30, "total_window_minutes": 60},
                    {"provider": "zero", "model": "m", "profile": "p", "tokens_used": 0, "token_budget": 0, "cost_usd": 0, "cost_budget_usd": 0, "elapsed_window_minutes": 0, "total_window_minutes": 60},
                ]
            }
        )
    )

    assert report["rows"][0]["at_risk"] is True
    assert report["rows"][0]["token_burn_ratio"] == 0.6
    assert report["summary"]["total_tokens_used"] == 60
    assert report["summary"]["total_cost_usd"] == 2.0
    assert report["summary"]["at_risk_count"] == 1
    assert report["summary"]["highest_projected_ratio"] == 1.2
