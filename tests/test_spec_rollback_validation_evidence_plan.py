from __future__ import annotations

import json

from max.spec import generate_rollback_validation_evidence_plan


def test_rollback_validation_evidence_plan_uses_hints() -> None:
    plan = generate_rollback_validation_evidence_plan(
        _spec(
            {
                "rollback_scenarios": [{"name": "schema rollback", "owner": "db"}],
                "evidence_artifacts": ["query log"],
                "validation_checks": ["read path smoke"],
                "reconciliation_steps": ["queue drain"],
                "signoffs": [{"name": "SRE signoff", "owner": "sre"}],
            }
        )
    )

    assert plan["rollback_scenarios"][0]["owner"] == "db"
    assert plan["signoffs"][0]["owner"] == "sre"
    assert plan["evidence_artifacts"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_rollback_validation_evidence_plan_defaults_sparse_input() -> None:
    plan = generate_rollback_validation_evidence_plan({"project": {"workflow_context": "checkout"}})

    assert plan["rollback_scenarios"][0]["name"] == "checkout rollback"
    assert plan["validation_checks"][0]["name"] == "post-rollback smoke check"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"rollback_validation_evidence": hints}, "evidence": {"signal_ids": ["sig-1"]}}
