from __future__ import annotations

import json

from max.spec import generate_incident_customer_credit_review_plan


def test_incident_customer_credit_review_plan_sorts_credit_records() -> None:
    plan = generate_incident_customer_credit_review_plan(
        _spec(
            "incident_customer_credit_review",
            {
                "affected_customers": [
                    {"customer": "Beta", "severity": "low", "credit_status": "ready"},
                    {"customer": "Acme", "severity": "high", "credit_status": "overdue", "incident": "INC-1"},
                ],
                "incidents": ["INC-1"],
                "sla_terms": ["99.9 SLA"],
                "proposed_credits": ["10 percent"],
                "approvers": ["finance"],
                "communications": ["customer notice"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.incident_customer_credit_review_plan.v1"
    assert [item["name"] for item in plan["customer_credit_records"]] == ["Acme", "Beta"]
    assert plan["customer_credit_records"][0]["incident"] == "INC-1"
    assert plan["approval_gates"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"incident_impact", "sla_eligibility", "proposed_credits", "customer_communications"}
    assert json.loads(json.dumps(plan)) == plan


def test_incident_customer_credit_review_plan_defaults_sparse_input() -> None:
    plan = generate_incident_customer_credit_review_plan({})

    assert plan["customer_credit_records"][0]["owner"] == "customer_success_owner"
    assert plan["proposed_credits"][0]["name"] == "credit calculation"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["inc-1"]}}
