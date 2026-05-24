from __future__ import annotations

import json

from max.spec.shadow_deployment_rollback_plan import generate_shadow_deployment_rollback_plan


def test_shadow_deployment_rollback_plan_includes_metrics_owner_actions_and_validation() -> None:
    plan = generate_shadow_deployment_rollback_plan(
        {
            "evidence": {"signal_ids": ["shadow-rollout"]},
            "metadata": {
                "shadow_deployment_rollback": {
                    "shadowed_components": [
                        {"component": "publisher adapter", "environment": "prod-shadow"},
                        {"model": "ranking-v3", "traffic": "mirrored"},
                    ],
                    "comparison_metrics": [
                        {"metric": "error delta", "threshold": "<= 0.5%"},
                        {"metric": "latency delta", "threshold": "p95 <= 10%"},
                    ],
                    "rollback_triggers": [{"name": "error delta breach", "threshold": "> 0.5% for 15 minutes"}],
                    "decision_owner_actions": [{"decision_owner": "release captain"}],
                    "communication_steps": ["notify SRE and support"],
                    "validation_checks": ["primary path error rate returns to baseline"],
                }
            },
        }
    )

    assert plan["schema_version"] == "max.spec.shadow_deployment_rollback_plan.v1"
    assert [component["name"] for component in plan["shadow_scope"]] == ["publisher adapter", "ranking-v3"]
    assert plan["comparison_metrics"][0]["threshold"] == "<= 0.5%"
    assert plan["rollback_triggers"][0]["threshold"] == "> 0.5% for 15 minutes"
    assert plan["decision_owner_actions"][0]["decision_owner"] == "release captain"
    assert plan["validation_checks"][0]["name"] == "primary path error rate returns to baseline"
    assert plan["rollback_risk_flags"][0]["severity"] == "low"
    assert json.loads(json.dumps(plan)) == plan


def test_shadow_deployment_rollback_plan_flags_missing_trigger_thresholds() -> None:
    plan = generate_shadow_deployment_rollback_plan(
        {"metadata": {"shadow_deployment_rollback": {"rollback_triggers": ["latency regression"]}}}
    )

    assert plan["rollback_risk_flags"][0]["severity"] == "high"
    assert plan["rollback_risk_flags"][0]["name"] == "missing rollback threshold for latency regression"
    assert plan["summary"]["high_risk_count"] == 1


def test_shadow_deployment_rollback_plan_defaults_and_stable_component_ordering() -> None:
    plan = generate_shadow_deployment_rollback_plan(
        {
            "metadata": {
                "shadow_deployment_rollback": {
                    "components": [
                        {"component": "zeta publisher"},
                        {"component": "alpha pipeline"},
                        {"component": "alpha pipeline"},
                    ]
                }
            }
        }
    )

    assert [component["name"] for component in plan["shadow_scope"]] == ["alpha pipeline", "zeta publisher"]
    assert plan["comparison_metrics"][0]["threshold"] == "p95 delta <= 10%"
    assert set(plan) >= {
        "shadow_scope",
        "comparison_metrics",
        "rollback_triggers",
        "decision_owner_actions",
        "communication_steps",
        "validation_checks",
    }
