from __future__ import annotations

from max.spec import generate_synthesis_queue_drain_plan


def test_synthesis_queue_drain_plan_orders_stale_batches_by_age_priority_and_profile() -> None:
    plan = generate_synthesis_queue_drain_plan(
        {
            "metadata": {
                "synthesis_queue_drain": {
                    "batches": [
                        {"id": "fresh", "profile": "growth", "priority": "critical", "age_hours": 2},
                        {"id": "older-low", "profile": "beta", "priority": "low", "age_hours": 80},
                        {"id": "same-age-high", "profile": "alpha", "priority": "high", "age_hours": 50},
                        {"id": "same-age-normal", "profile": "alpha", "priority": "normal", "age_hours": 50},
                    ]
                }
            }
        }
    )

    assert [row["id"] for row in plan["queue_inventory"]] == ["older-low", "same-age-high", "same-age-normal", "fresh"]
    assert plan["summary"]["stale_batch_count"] == 3
    assert plan["priority_order"][0]["batch_id"] == "older-low"
    assert plan["batching_strategy"][0]["name"] == "stale_first"


def test_synthesis_queue_drain_plan_includes_budget_and_rate_limit_safeguards() -> None:
    plan = generate_synthesis_queue_drain_plan({"queue": [{"id": "b1", "queued_hours": 30, "provider": "openai"}]})

    assert [item["name"] for item in plan["budget_guardrails"]] == ["daily_budget_cap", "per_profile_quota", "cost_recheck"]
    assert [item["name"] for item in plan["rate_limit_safeguards"]] == ["provider_window", "retry_backoff", "concurrency_limit"]
    assert plan["verification_steps"][1]["name"] == "budget_and_rate_limit_audit"


def test_synthesis_queue_drain_plan_empty_queue_returns_no_action_with_validation() -> None:
    plan = generate_synthesis_queue_drain_plan({})

    assert plan["summary"]["action"] == "no_action"
    assert plan["queue_inventory"] == []
    assert plan["batching_strategy"][0]["name"] == "no_action"
    assert plan["verification_steps"][2]["name"] == "empty_queue_validation"
