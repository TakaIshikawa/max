from __future__ import annotations

import json

from max.spec import generate_data_warehouse_access_review_plan


def test_data_warehouse_access_review_plan_covers_exceptions_and_audit_artifacts() -> None:
    plan = generate_data_warehouse_access_review_plan(
        _spec(
            {
                "roles": [
                    {
                        "role": "analyst_read",
                        "dataset": "signal_exports",
                        "owner": "analytics_owner",
                        "purpose": "insight review",
                    },
                    {
                        "group": "spec_admins",
                        "dataset": "generated_specs",
                        "classification": "restricted",
                    },
                ],
                "datasets": [
                    {"dataset": "generated_specs", "classification": "restricted"},
                    {"table": "signal_exports", "classification": "internal"},
                ],
                "exceptions": [{"role": "spec_admins", "dataset": "generated_specs", "expiry": "2026-06-30"}],
                "remediation": [{"name": "remove dormant analysts", "deadline": "2026-06-15"}],
                "audit_artifacts": ["grant export and reviewer attestation"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.data_warehouse_access_review_plan.v1"
    assert [item["name"] for item in plan["access_inventory"]] == ["analyst_read", "spec_admins"]
    assert plan["access_inventory"][0]["dataset"] == "signal_exports"
    assert plan["dataset_inventory"][0]["name"] == "generated_specs"
    assert plan["exception_handling"][0]["role"] == "spec_admins"
    assert plan["remediation_schedule"][0]["deadline"] == "2026-06-15"
    assert plan["audit_artifacts"][0]["name"] == "grant export and reviewer attestation"
    assert json.loads(json.dumps(plan)) == plan


def test_data_warehouse_access_review_plan_defaults_empty_roles_and_sections() -> None:
    plan = generate_data_warehouse_access_review_plan({})

    assert plan["access_inventory"][0]["role"] == "warehouse reader"
    assert plan["dataset_inventory"][0]["name"] == (
        "exported signals, insights, evaluations, and generated specs"
    )
    assert set(plan) >= {
        "scope",
        "access_inventory",
        "review_procedure",
        "exception_handling",
        "remediation_schedule",
        "audit_artifacts",
    }


def _spec(hints: dict) -> dict:
    return {"metadata": {"data_warehouse_access_review": hints}, "evidence": {"signal_ids": ["dw-1"]}}
