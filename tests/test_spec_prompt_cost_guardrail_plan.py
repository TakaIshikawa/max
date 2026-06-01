from __future__ import annotations

import pytest

from max.spec.prompt_cost_guardrail_plan import generate_prompt_cost_guardrail_plan


def test_prompt_cost_guardrail_plan_validates_threshold() -> None:
    with pytest.raises(ValueError):
        generate_prompt_cost_guardrail_plan([], [], alert_threshold=0)

    with pytest.raises(ValueError):
        generate_prompt_cost_guardrail_plan([], [], alert_threshold=1.1)


def test_prompt_cost_guardrail_plan_blocks_over_budget_prompts() -> None:
    plan = generate_prompt_cost_guardrail_plan(
        [{"prompt_id": "p1", "projected_spend": 120, "owner": "sales"}],
        [{"prompt_id": "p1", "cost_cap": 100, "budget_id": "b1"}],
    )

    assert plan["budget_matches"][0]["status"] == "blocked"
    assert plan["remediation_actions"][0]["severity"] == "critical"
    assert "hard cost cap" in plan["remediation_actions"][0]["action"]


def test_prompt_cost_guardrail_plan_matches_budget_by_prompt_family_and_model() -> None:
    plan = generate_prompt_cost_guardrail_plan(
        [
            {"prompt_id": "exact", "family": "sales", "model": "gpt-a", "projected_spend": 10},
            {"prompt_id": "family-only", "family": "support", "model": "gpt-b", "projected_spend": 20},
            {"prompt_id": "model-only", "model": "gpt-c", "projected_spend": 30},
        ],
        [
            {"budget_id": "model-budget", "model": "gpt-c", "cost_cap": 50},
            {"budget_id": "family-budget", "family": "support", "cost_cap": 40},
            {"budget_id": "prompt-budget", "prompt_id": "exact", "cost_cap": 25},
        ],
    )

    matches = {row["prompt_id"]: row["budget_id"] for row in plan["budget_matches"]}
    assert matches == {"exact": "prompt-budget", "family-only": "family-budget", "model-only": "model-budget"}


def test_prompt_cost_guardrail_plan_sorts_remediation_by_spend_with_stable_tie_breaking() -> None:
    plan = generate_prompt_cost_guardrail_plan(
        [
            {"prompt_id": "b", "projected_spend": 80, "cost_cap": 100},
            {"prompt_id": "a", "projected_spend": 80, "cost_cap": 100},
            {"prompt_id": "c", "projected_spend": 120, "cost_cap": 100},
            {"prompt_id": "healthy", "projected_spend": 10, "cost_cap": 100},
        ],
        [],
        alert_threshold=0.8,
    )

    assert [row["prompt_id"] for row in plan["remediation_actions"]] == ["c", "a", "b"]
    assert plan["remediation_actions"][1]["severity"] == "warning"
