from __future__ import annotations

from max.spec import generate_llm_budget_reallocation_plan


def test_llm_budget_reallocation_plan_orders_over_budget_before_under_utilized() -> None:
    plan = generate_llm_budget_reallocation_plan(
        {
            "metadata": {
                "llm_budget_reallocation": {
                    "allocations": [
                        {"id": "under", "profile": "p", "stage": "draft", "provider": "openai", "model": "small", "budget_tokens": 100, "used_tokens": 20, "budget_cost": 2, "used_cost": 0.2, "output_value": 0.8},
                        {"id": "over", "profile": "p", "stage": "eval", "provider": "openai", "model": "large", "budget_tokens": 100, "used_tokens": 130, "budget_cost": 2, "used_cost": 2.4, "output_value": 0.9},
                    ]
                }
            }
        }
    )

    assert [row["id"] for row in plan["current_allocation_summary"]] == ["over", "under"]
    assert [point["status"] for point in plan["pressure_points"]] == ["over_budget", "under_utilized"]
    assert plan["recommended_reallocations"][0]["allocation_id"] == "over"
    assert plan["guardrails"][0]["name"] == "provider_cap"


def test_llm_budget_reallocation_plan_zero_budget_avoids_division_errors() -> None:
    plan = generate_llm_budget_reallocation_plan({"allocations": [{"id": "zero", "stage": "ideation", "used_tokens": 10, "used_cost": 1}]})

    assert plan["current_allocation_summary"][0]["token_utilization"] == 0.0
    assert plan["current_allocation_summary"][0]["status"] == "zero_budget"
    assert "explicit starter budget" in plan["recommended_reallocations"][0]["action"]
