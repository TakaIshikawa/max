from __future__ import annotations

from max.spec.privileged_action_audit_plan import REQUIRED_LOG_FIELDS, generate_privileged_action_audit_plan


def test_privileged_action_audit_plan_includes_required_fields_for_each_action() -> None:
    plan = generate_privileged_action_audit_plan({"metadata": {"privileged_action_audit": {"actions": [{"action": "rotate key", "actor_role": "sre", "log_destination": "siem", "retention_requirement": "1 year"}]}}})

    assert plan["privileged_actions"][0]["required_log_fields"] == REQUIRED_LOG_FIELDS


def test_privileged_action_audit_plan_missing_fields_create_blockers() -> None:
    plan = generate_privileged_action_audit_plan({"metadata": {"privileged_action_audit": {"actions": [{"action": "rotate key"}]}}})

    assert [row["name"] for row in plan["blockers"]] == ["missing actor role for rotate key", "missing log destination for rotate key", "missing retention requirement for rotate key"]


def test_privileged_action_audit_plan_has_deterministic_review_and_escalation() -> None:
    plan = generate_privileged_action_audit_plan({})

    assert plan["review_cadence"][0]["name"] == "daily high-risk review and weekly aggregate review"
    assert plan["escalation_path"][0]["name"].startswith("security incident commander")
