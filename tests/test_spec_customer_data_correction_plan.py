from __future__ import annotations

import json

from max.spec import generate_customer_data_correction_plan


def test_customer_data_correction_plan_normalizes_and_sorts_fields() -> None:
    plan = generate_customer_data_correction_plan(
        _spec(
            "customer_data_correction",
            {
                "corrections": [
                    {"field": "address", "severity": "low", "deadline_status": "ready"},
                    {"field": "tax_id", "severity": "high", "deadline_status": "overdue", "system": "billing"},
                ],
                "systems": ["billing"],
                "correction_actions": ["update source of truth"],
                "validation_checks": ["customer record check"],
                "customer_communications": ["completion notice"],
                "audit_evidence": ["audit log"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.customer_data_correction_plan.v1"
    assert [item["name"] for item in plan["correction_items"]] == ["tax_id", "address"]
    assert plan["correction_items"][0]["field"] == "tax_id"
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"affected_systems", "correction_actions", "customer_notifications", "audit_evidence"}
    assert json.loads(json.dumps(plan)) == plan


def test_customer_data_correction_plan_defaults_sparse_input() -> None:
    plan = generate_customer_data_correction_plan({})

    assert plan["correction_items"][0]["owner"] == "privacy_owner"
    assert plan["audit_evidence"][0]["name"] == "correction audit trail"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["corr-1"]}}
