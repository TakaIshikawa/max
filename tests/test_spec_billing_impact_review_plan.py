from __future__ import annotations

import json

from max.spec import generate_billing_impact_review_plan


def test_billing_impact_review_plan_uses_hints_and_sorts_risks() -> None:
    plan = generate_billing_impact_review_plan(
        _spec(
            "billing_impact_review",
            {
                "affected_plans": ["Pro", "Basic", "Pro"],
                "charge_risks": [
                    {"name": "missing invoice preview", "severity": "medium", "status": "missing"},
                    {"name": "tax overcharge", "severity": "critical", "status": "ready"},
                    {"name": "proration mismatch", "severity": "high", "status": "overdue"},
                    {"name": "tax overcharge", "severity": "critical", "status": "ready"},
                ],
                "refund_credit_actions": ["issue credit memo"],
                "owner_approvals": ["finance signoff"],
                "customer_communications": ["billing FAQ"],
                "validation_checks": ["invoice preview dry run"],
            },
        )
    )

    assert [item["name"] for item in plan["affected_plans"]] == ["Basic", "Pro"]
    assert [item["name"] for item in plan["charge_risks"]] == [
        "tax overcharge",
        "proration mismatch",
        "missing invoice preview",
    ]
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_billing_impact_review_plan_defaults_sparse_input() -> None:
    plan = generate_billing_impact_review_plan({})

    assert plan["affected_plans"][0]["name"] == "default subscription plan"
    assert plan["charge_risks"][0]["name"] == "billing impact review"
    assert set(plan) >= {
        "refund_credit_actions",
        "owner_approvals",
        "customer_communications",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
