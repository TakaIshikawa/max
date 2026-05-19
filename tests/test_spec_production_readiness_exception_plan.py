from __future__ import annotations

import json

from max.spec.production_readiness_exception_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_production_readiness_exception_plan,
)


def test_production_readiness_exception_plan_tightens_high_risk_launch_blocker() -> None:
    plan = generate_production_readiness_exception_plan(
        {
            "project": {"title": "Checkout Launch", "buyer": "GM"},
            "metadata": {
                "production_readiness_exception": {
                    "unmet_controls": ["load test"],
                    "compensating_controls": ["traffic cap"],
                    "launch_blocking": True,
                    "risk_level": "critical",
                    "approvers": ["VP Engineering"],
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["launch_blocking"] is True
    assert plan["summary"]["exception_risk"] == "high"
    assert plan["expiry_and_review"][1]["description"] == "Review daily until closure."
    assert plan["approval_workflow"][0]["owner"] == "VP Engineering"
    assert plan["launch_constraints"][0]["severity"] == "high"
    json.dumps(plan)


def test_production_readiness_exception_plan_defaults_sparse_input() -> None:
    plan = generate_production_readiness_exception_plan({})

    assert [item["name"] for item in plan["unmet_controls"]] == ["observability sign-off", "rollback rehearsal evidence"]
    assert [item["name"] for item in plan["compensating_controls"]] == ["daily owner review", "manual rollback checkpoint"]
    assert plan["summary"]["expiry"] == "30 days after approval"
    assert len(plan["owner_roles"]) == 4
