from __future__ import annotations

import json

from max.spec import generate_rollout_decision_log_plan as exported_generator
from max.spec.rollout_decision_log_plan import KIND, SCHEMA_VERSION, generate_rollout_decision_log_plan


def test_rollout_decision_log_plan_uses_decisions_approvers_and_publication_hints() -> None:
    plan = generate_rollout_decision_log_plan(
        {
            "metadata": {
                "rollout_decision_log": {
                    "decisions": [{"decision": "expand beta", "status": "approved", "rationale": "metrics pass", "approver": "gm"}],
                    "approvers": ["gm"],
                    "revisit_triggers": ["support spike"],
                    "publication_channels": ["launch channel"],
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["decision_entries"][0]["decision"] == "expand beta"
    assert plan["decision_entries"][0]["status"] == "approved"
    assert plan["approvers"][0]["role"] == "gm"
    assert plan["publication_notes"][0]["channel"] == "launch channel"
    assert exported_generator({})["kind"] == KIND


def test_rollout_decision_log_plan_sparse_defaults_use_project_and_recommendation_context() -> None:
    spec = {"project": {"title": "Checkout Launch"}, "evaluation": {"recommendation": "monitor"}}
    first = generate_rollout_decision_log_plan(spec)
    second = generate_rollout_decision_log_plan(spec)

    assert first == second
    assert first["decision_entries"][0]["decision"] == "Rollout decision for Checkout Launch"
    assert "monitor" in first["decision_entries"][0]["rationale"]
    assert json.loads(json.dumps(first))["kind"] == KIND
