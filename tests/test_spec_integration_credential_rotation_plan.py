from __future__ import annotations

import json

from max.spec import generate_integration_credential_rotation_plan


def test_integration_credential_rotation_plan_sorts_credentials() -> None:
    plan = generate_integration_credential_rotation_plan(
        _spec(
            "integration_credential_rotation",
            {
                "credentials": [
                    {"name": "maps token", "severity": "low", "rotation_date": "ready"},
                    {"name": "payments key", "severity": "critical", "rotation_date": "expired"},
                    {"name": "crm secret", "severity": "high", "rotation_date": "missing"},
                    {"name": "payments key", "severity": "critical", "rotation_date": "expired"},
                ],
                "rotation_sequence": ["create new key"],
                "dependent_services": ["checkout"],
                "rollback_path": ["restore previous key"],
                "owner_approvals": ["security approval"],
                "partner_notices": ["partner notice"],
                "validation_checks": ["credential smoke test"],
            },
        )
    )

    assert [item["name"] for item in plan["credential_inventory"]] == [
        "payments key",
        "crm secret",
        "maps token",
    ]
    assert plan["credential_inventory"][0]["rotation_date"] == "expired"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_integration_credential_rotation_plan_defaults_sparse_input() -> None:
    plan = generate_integration_credential_rotation_plan({})

    assert plan["credential_inventory"][0]["name"] == "integration credential"
    assert set(plan) >= {
        "rotation_sequence",
        "dependent_services",
        "rollback_path",
        "owner_approvals",
        "partner_notices",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
