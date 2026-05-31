from __future__ import annotations

from max.spec.adapter_rate_limit_recovery_plan import generate_adapter_rate_limit_recovery_plan


def test_adapter_rate_limit_recovery_plan_handles_exhausted_quota() -> None:
    plan = generate_adapter_rate_limit_recovery_plan(
        {
            "metadata": {
                "adapter_rate_limit_recovery": {
                    "adapters": [
                        {"id": "crm", "adapter": "CRM", "remaining_quota": 0, "quota_limit": 1000, "reset_at": "2026-06-01T00:00:00Z"}
                    ]
                }
            }
        }
    )

    assert plan["adapter_recovery_windows"][0]["risk"] == "exhausted"
    assert plan["summary"]["highest_risk_adapter"] == "CRM"
    assert "hold noncritical traffic" in plan["summary"]["recommendation"]
    assert "pause noncritical requests" in plan["quota_conservation_steps"][0]["action"]
    assert plan["verification_gates"][0]["name"] == "quota_available_after_reset"


def test_adapter_rate_limit_recovery_plan_handles_partial_degradation() -> None:
    plan = generate_adapter_rate_limit_recovery_plan(
        {"incidents": [{"id": "billing", "name": "Billing", "remaining": 80, "limit": 100, "status": "partial", "impact": "invoice sync delayed"}]}
    )

    adapter = plan["adapter_recovery_windows"][0]
    assert adapter["risk"] == "high"
    assert adapter["quota_utilization"] == 0.2
    assert plan["stakeholder_impact"][0]["impact"] == "invoice sync delayed"
    assert any(step["action"] == "confirm provider quota reset time and update the recovery window" for step in plan["quota_conservation_steps"])


def test_adapter_rate_limit_recovery_plan_sorts_multiple_adapters_by_highest_risk() -> None:
    plan = generate_adapter_rate_limit_recovery_plan(
        {
            "adapters": [
                {"id": "search", "name": "Search", "remaining_quota": 900, "quota_limit": 1000, "reset_at": "known"},
                {"id": "mail", "name": "Mail", "remaining_quota": 40, "quota_limit": 1000, "reset_at": "known"},
                {"id": "crm", "name": "CRM", "remaining_quota": 0, "quota_limit": 1000, "reset_at": "known"},
            ]
        }
    )

    assert [adapter["id"] for adapter in plan["adapter_recovery_windows"]] == ["crm", "mail", "search"]
    assert plan["summary"]["highest_risk_adapter"] == "CRM"
    assert "CRM" in plan["summary"]["recommendation"]


def test_adapter_rate_limit_recovery_plan_represents_missing_reset_times_as_unknowns() -> None:
    plan = generate_adapter_rate_limit_recovery_plan({"adapters": [{"id": "ads", "name": "Ads", "remaining_quota": 500, "quota_limit": 1000}]})

    adapter = plan["adapter_recovery_windows"][0]
    assert adapter["reset_at"] == "unknown"
    assert adapter["reset_time_known"] is False
    assert plan["backoff_policy_checks"][2]["name"] == "reset_time_follow_up"
    assert any("confirm provider quota reset time" in step["action"] for step in plan["quota_conservation_steps"])
