from __future__ import annotations

from max.spec.prompt_evaluation_coverage_plan import generate_prompt_evaluation_coverage_plan


def test_prompt_evaluation_coverage_high_risk_uncovered_first() -> None:
    plan = generate_prompt_evaluation_coverage_plan({"metadata": {"prompt_evaluation_coverage": {"prompts": [{"prompt": "low", "coverage_status": "covered"}, {"prompt": "triage", "risk": "high", "coverage_status": "missing"}]}}})
    assert plan["prompt_inventory"][0]["name"] == "triage"
    assert "Prioritize uncovered high-risk prompt" in plan["risk_gaps"][0]["description"]
    assert plan["scenario_coverage"] and plan["golden_set_links"] and plan["refresh_cadence"]


def test_prompt_evaluation_coverage_empty_inventory_bootstraps() -> None:
    plan = generate_prompt_evaluation_coverage_plan({})
    assert plan["prompt_inventory"][0]["coverage_status"] == "missing"
    assert plan["bootstrap_checklist"]
