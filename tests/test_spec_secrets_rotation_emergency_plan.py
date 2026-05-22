from __future__ import annotations

import json

from max.spec import generate_secrets_rotation_emergency_plan


def test_secrets_rotation_emergency_plan_orders_high_risk_secrets() -> None:
    plan = generate_secrets_rotation_emergency_plan(
        _spec(
            "secrets_rotation_emergency",
            {
                "secrets": [
                    {"secret": "analytics token", "system": "warehouse", "severity": "low"},
                    {"secret": "prod database password", "system": "billing", "severity": "critical"},
                ],
                "systems": ["billing"],
                "owners": ["security lead"],
                "rotation_order": ["revoke suspect credential"],
                "validation": ["billing smoke test"],
                "containment": ["disable old credential"],
                "communications": ["incident channel update"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.secrets_rotation_emergency_plan.v1"
    assert [item["name"] for item in plan["affected_secrets"]] == ["prod database password", "analytics token"]
    assert set(plan) >= {"affected_systems", "owner_assignments", "rotation_phases", "validation_checks", "containment_rollback", "communications"}
    assert json.loads(json.dumps(plan)) == plan


def test_secrets_rotation_emergency_plan_defaults_sparse_input() -> None:
    plan = generate_secrets_rotation_emergency_plan({})

    assert plan["affected_secrets"][0]["owner"] == "security_owner"
    assert plan["rotation_phases"][0]["name"] == "contain, revoke, rotate, deploy, validate, and monitor"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["sre-1"]}}
