from __future__ import annotations

import json

from max.spec import generate_model_provider_failover_plan


def test_model_provider_failover_plan_prioritizes_provider_risks() -> None:
    plan = generate_model_provider_failover_plan(
        _spec(
            "model_provider_failover",
            {
                "providers": [
                    {"provider": "Provider B", "model": "large", "severity": "low", "impact": "latency"},
                    {"provider": "Provider A", "model": "large", "severity": "critical", "impact": "outage"},
                ],
                "triggers": ["provider outage"],
                "compatibility_checks": ["tool schema compatibility"],
                "validation": ["golden prompt regression"],
                "budget_guardrails": ["daily spend cap"],
                "rollout": ["10 percent canary"],
                "monitoring": ["quality dashboard"],
                "rollback": ["restore primary routing"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.model_provider_failover_plan.v1"
    assert [item["name"] for item in plan["provider_inventory"]] == ["Provider A", "Provider B"]
    assert set(plan) >= {"failover_triggers", "compatibility_checks", "prompt_regression_validation", "budget_guardrails", "monitoring", "rollback"}
    assert json.loads(json.dumps(plan)) == plan


def test_model_provider_failover_plan_defaults_sparse_input() -> None:
    plan = generate_model_provider_failover_plan({})

    assert plan["provider_inventory"][0]["owner"] == "ml_platform_owner"
    assert plan["budget_guardrails"][0]["name"] == "cost cap and spend anomaly alert"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["mpf-1"]}}
