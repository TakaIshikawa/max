from __future__ import annotations

import json

from max.spec import generate_entitlement_sunset_exception_plan


def test_entitlement_sunset_exception_plan_sorts_and_dedupes() -> None:
    plan = generate_entitlement_sunset_exception_plan(
        _spec(
            "entitlement_sunset_exception",
            {
                "entitlements": [
                    {"name": "Legacy API", "severity": "low", "expiration": "2026-09-01"},
                    {"name": "Admin Override", "severity": "high", "expiration": "expired"},
                    {"name": "Admin Override", "severity": "high"},
                ],
                "affected_customers": ["Acme"],
                "approval_owners": ["VP Product"],
                "migration_paths": ["standard entitlement"],
                "kill_criteria": ["no active customers"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.entitlement_sunset_exception_plan.v1"
    assert plan["kind"] == "max.spec.entitlement_sunset_exception_plan"
    assert [item["name"] for item in plan["entitlement_exceptions"]] == ["Admin Override", "Legacy API"]
    assert plan["approval_gates"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"customer_impact", "migration_paths", "kill_criteria", "evidence_checks"}
    assert json.loads(json.dumps(plan)) == plan


def test_entitlement_sunset_exception_plan_defaults_sparse_input() -> None:
    plan = generate_entitlement_sunset_exception_plan({})

    assert plan["entitlement_exceptions"][0]["owner"] == "product_owner"
    assert plan["migration_paths"][0]["name"] == "replacement entitlement path"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["sig-1"]}}
