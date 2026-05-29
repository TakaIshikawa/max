from __future__ import annotations

from max.spec import generate_spec_approval_escalation_plan


def test_spec_approval_escalation_plan_assigned_unassigned_and_overdue() -> None:
    plan = generate_spec_approval_escalation_plan({"metadata": {"spec_approval_escalation": {"blocked_specs": [{"name": "spec-a", "assignee": "alex", "due_at": "2026-05-28T00:00:00+00:00"}, {"name": "spec-b", "due_at": "2026-05-30T00:00:00+00:00"}]}}}, now="2026-05-29T00:00:00+00:00")
    assert plan["blocked_specs"][0]["assignee"] == "alex"
    assert plan["blocked_specs"][0]["overdue_hours"] == 24
    assert plan["blocked_specs"][1]["assignee"] == "unassigned"
    assert plan["summary"]["overdue_count"] == 1


def test_spec_approval_escalation_plan_minimal_defaults() -> None:
    plan = generate_spec_approval_escalation_plan({})
    assert plan["blocked_specs"]
    assert plan["escalation_path"]
    assert plan["fallback_decisions"]
