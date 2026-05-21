from __future__ import annotations

import json

from max.spec import generate_vendor_security_reassessment_plan


def test_vendor_security_reassessment_plan_sorts_by_risk_and_due_status() -> None:
    plan = generate_vendor_security_reassessment_plan(
        _spec(
            "vendor_security_reassessment",
            {
                "vendors": [
                    {"vendor": "Beta", "severity": "medium", "due_status": "ready"},
                    {"vendor": "Acme", "severity": "critical", "due_status": "missing"},
                ],
                "risk_drivers": ["expired SOC2"],
                "evidence_gaps": ["missing pen test"],
                "controls": ["DPA control"],
                "approval_outcomes": ["security approval"],
                "follow_up_actions": ["renew attestation"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.vendor_security_reassessment_plan.v1"
    assert [item["name"] for item in plan["vendor_reassessments"]] == ["Acme", "Beta"]
    assert plan["evidence_gaps"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"risk_drivers", "control_reviews", "approval_decisions", "follow_up_actions"}
    assert json.loads(json.dumps(plan)) == plan


def test_vendor_security_reassessment_plan_defaults_sparse_input() -> None:
    plan = generate_vendor_security_reassessment_plan({})

    assert plan["vendor_reassessments"][0]["owner"] == "vendor_owner"
    assert plan["evidence_gaps"][0]["name"] == "current security attestation"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["vendor-1"]}}
