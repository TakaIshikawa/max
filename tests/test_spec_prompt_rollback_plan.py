from __future__ import annotations

from max.spec.prompt_rollback_plan import generate_prompt_rollback_plan


def test_prompt_rollback_orders_critical_prompts_and_sections() -> None:
    plan = generate_prompt_rollback_plan({"metadata": {"prompt_rollback": {"prompts": [{"prompt": "normal", "severity": "low", "previous_version": "v1"}, {"prompt": "critical", "severity": "critical", "previous_version": "v2"}]}}})
    assert [row["name"] for row in plan["impacted_prompts"]] == ["critical", "normal"]
    assert plan["rollback_triggers"] and plan["validation_steps"] and plan["communication"] and plan["monitoring_windows"]


def test_prompt_rollback_flags_missing_previous_version() -> None:
    plan = generate_prompt_rollback_plan({"metadata": {"prompt_rollback": {"prompt_templates": [{"template": "triage", "previous_version": "missing"}]}}})
    assert "Missing previous prompt version" in plan["risk_flags"][0]["description"]


def test_prompt_rollback_is_deterministic() -> None:
    payload = {"metadata": {"prompt_rollback": {"prompts": [{"prompt": "b", "previous_version": "v1"}, {"prompt": "a", "previous_version": "v1"}]}}}
    assert generate_prompt_rollback_plan(payload) == generate_prompt_rollback_plan(payload)
