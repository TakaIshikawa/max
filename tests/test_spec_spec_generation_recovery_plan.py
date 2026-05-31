from __future__ import annotations

from max.spec.spec_generation_recovery_plan import generate_spec_generation_recovery_plan


def test_spec_generation_recovery_groups_by_reason_and_profile_or_template() -> None:
    plan = generate_spec_generation_recovery_plan({"metadata": {"spec_generation_recovery": {"failures": [{"job_id": "j2", "reason": "transient_timeout", "profile": "enterprise"}, {"job_id": "j1", "reason": "transient_timeout", "profile": "enterprise"}, {"job_id": "j3", "reason": "missing_evidence", "template": "privacy"}]}}})
    assert [group["name"] for group in plan["failure_groups"]] == ["missing_evidence / privacy", "transient_timeout / enterprise"]
    assert plan["failure_groups"][1]["job_ids"] == ["j1", "j2"]
    assert plan["retry_order"] and plan["validation_steps"] and plan["rollback_steps"]


def test_spec_generation_recovery_distinguishes_budget_and_missing_evidence() -> None:
    plan = generate_spec_generation_recovery_plan({"metadata": {"spec_generation_recovery": {"jobs": [{"id": "budget", "reason": "budget_exhaustion"}, {"id": "evidence", "reason": "missing_evidence"}]}}})
    descriptions = " ".join(action["description"] for action in plan["repair_actions"] + plan["budget_checks"])
    assert "Reallocate LLM budget" in descriptions
    assert "Attach missing evidence ids" in descriptions
    assert [group["reason"] for group in plan["failure_groups"]] == ["budget_exhaustion", "missing_evidence"]


def test_spec_generation_recovery_no_failures_renders_clear_checklist() -> None:
    plan = generate_spec_generation_recovery_plan({})
    assert plan["failure_groups"][0]["reason"] == "none"
    assert plan["validation_steps"]
