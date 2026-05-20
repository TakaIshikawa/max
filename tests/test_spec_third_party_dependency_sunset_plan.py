from __future__ import annotations

import json

from max.spec import generate_third_party_dependency_sunset_plan


def test_third_party_dependency_sunset_plan_uses_hints() -> None:
    plan = generate_third_party_dependency_sunset_plan(
        _spec(
            {
                "dependency_name": "LegacyPay",
                "replacement_path": "DirectPay",
                "affected_integrations": ["checkout"],
                "migration_steps": ["dual write"],
                "risk_controls": ["parallel run"],
                "customer_communications": ["merchant notice"],
                "validation_checks": ["parity test"],
            }
        )
    )

    assert plan["dependency_profile"]["name"] == "LegacyPay"
    assert plan["replacement_path"]["path"] == "DirectPay"
    assert plan["affected_integrations"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_third_party_dependency_sunset_plan_defaults_sparse_input() -> None:
    plan = generate_third_party_dependency_sunset_plan({})

    assert plan["dependency_profile"]["name"] == "third-party dependency"
    assert plan["migration_steps"][0]["name"] == "migrate dependency usage"
    assert json.loads(json.dumps(plan)) == plan


def _spec(hints: dict) -> dict:
    return {"metadata": {"third_party_dependency_sunset": hints}, "evidence": {"signal_ids": ["sig-1"]}}
