from __future__ import annotations

from max.spec.model_rollback_criteria_plan import generate_model_rollback_criteria_plan


def test_model_rollback_criteria_plan_reflects_hints() -> None:
    plan = generate_model_rollback_criteria_plan({"metadata": {"model_rollback_criteria": {"rollback_triggers": [{"trigger": "safety score drop", "severity": "critical"}], "metric_thresholds": [{"metric": "toxicity", "threshold": ">0.02"}], "approval_gates": ["release owner signoff"], "validation_evidence": ["canary replay"], "customer_impact_checks": ["enterprise tenant review"], "post_rollback_monitoring": ["support ticket watch"]}}})

    assert set(plan) >= {"schema_version", "kind", "source", "summary", "rollback_triggers", "metric_thresholds", "approval_gates", "validation_evidence", "customer_impact_checks", "post_rollback_monitoring", "evidence_references"}
    assert plan["rollback_triggers"][0]["name"] == "safety score drop"
    assert plan["metric_thresholds"][0]["metric"] == "toxicity"
    assert plan["approval_gates"][0]["name"] == "release owner signoff"


def test_model_rollback_criteria_plan_defaults() -> None:
    plan = generate_model_rollback_criteria_plan({})

    assert plan["rollback_triggers"]
    assert plan["metric_thresholds"]
    assert plan["schema_version"] == "max.spec.model_rollback_criteria_plan.v1"
