from __future__ import annotations

from max.spec.inference_rate_limit_exception_plan import generate_inference_rate_limit_exception_plan


def test_inference_rate_limit_exception_plan_approved_temporary_exception() -> None:
    plan = generate_inference_rate_limit_exception_plan(
        {"exceptions": [{"tenant": "enterprise-a", "requester": "sales", "business_justification": "launch load test", "current_limit": "100 rpm", "proposed_limit": "500 rpm", "budget_impact": "$120/day", "safety_monitoring": "abuse dashboard", "expiry": "2026-06-30", "approver": "platform"}]}
    )

    assert plan["blockers"] == []
    assert plan["warnings"] == []
    assert set(plan) >= {"exception_requests", "business_justification", "limit_delta", "budget_impact", "safety_monitoring", "expiry", "approval_gates", "rollback"}
    assert plan["limit_delta"][0]["current_limit"] == "100 rpm"


def test_inference_rate_limit_exception_plan_blocks_missing_expiry_and_warns_budget() -> None:
    source = {"exceptions": [{"tenant": "enterprise-b", "approver": "platform", "safety_monitoring": "abuse dashboard", "metadata": {"segment": "strategic"}}]}
    plan = generate_inference_rate_limit_exception_plan(source)

    assert [row["missing_field"] for row in plan["blockers"]] == ["expiry"]
    assert [row["name"] for row in plan["warnings"]] == ["missing budget impact for enterprise-b"]
    assert generate_inference_rate_limit_exception_plan(source) == plan
    assert plan["exception_requests"][0]["metadata"] == {"segment": "strategic"}
