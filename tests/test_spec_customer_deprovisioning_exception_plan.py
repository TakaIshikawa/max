from __future__ import annotations

from max.spec import generate_customer_deprovisioning_exception_plan


def test_customer_deprovisioning_exception_plan_covers_exception_workflow() -> None:
    plan = generate_customer_deprovisioning_exception_plan(
        {
            "metadata": {
                "customer_deprovisioning_exception": {
                    "rationale": ["legal hold for workspace export"],
                    "workspaces": [{"workspace": "acme-prod", "customer": "Acme", "role": "read-only"}],
                    "controls": ["daily access review"],
                    "expiration_date": [{"name": "2026-07-01", "expiration": "2026-07-01"}],
                    "approvals": ["customer owner approval"],
                    "customer_notification": ["send exception notice"],
                    "audit_evidence": ["approval ticket"],
                }
            }
        }
    )

    assert plan["retained_access"][0]["name"] == "acme-prod"
    assert plan["required_follow_up"] == []
    assert set(plan) >= {"exception_rationale", "compensating_controls", "expiration", "owner_approvals", "customer_notification", "audit_evidence"}


def test_customer_deprovisioning_exception_plan_requires_missing_expiration() -> None:
    plan = generate_customer_deprovisioning_exception_plan({})

    assert plan["required_follow_up"][0]["name"] == "Expiration date required"
    assert plan["retained_access"][0]["name"] == "retained customer access exception"
