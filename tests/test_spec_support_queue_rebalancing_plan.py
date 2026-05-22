from __future__ import annotations

import json

from max.spec import generate_support_queue_rebalancing_plan


def test_support_queue_rebalancing_plan_orders_backlog_and_sla_risk() -> None:
    plan = generate_support_queue_rebalancing_plan(
        _spec(
            "support_queue_rebalancing",
            {
                "queues": [
                    {"queue": "tier 2", "backlog": 20, "sla_risk": "normal", "severity": "low"},
                    {"queue": "billing", "backlog": 5, "sla_risk": "breach risk", "severity": "medium"},
                    {"queue": "enterprise", "backlog": 100, "sla_risk": "normal", "severity": "high"},
                ],
                "routing": ["shift billing to vendor"],
                "staffing": ["two extra tier 2 agents"],
                "sla_impact": ["billing first response risk"],
                "escalations": ["manager escalation"],
                "communications": ["agent notice"],
                "monitoring": ["backlog dashboard"],
                "rollback": ["restore old routing"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.support_queue_rebalancing_plan.v1"
    assert [item["name"] for item in plan["queue_baseline"]] == ["billing", "enterprise", "tier 2"]
    assert set(plan) >= {"routing_changes", "staffing_assumptions", "sla_customer_impact", "escalation_paths", "communications", "monitoring", "rollback"}
    assert json.loads(json.dumps(plan)) == plan


def test_support_queue_rebalancing_plan_defaults_sparse_input() -> None:
    plan = generate_support_queue_rebalancing_plan({})

    assert plan["queue_baseline"][0]["owner"] == "support_owner"
    assert plan["rollback"][0]["name"] == "restore previous routing and staffing allocation"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["sqr-1"]}}
