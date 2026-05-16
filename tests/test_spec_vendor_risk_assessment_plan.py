from __future__ import annotations

from max.spec.vendor_risk_assessment_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_vendor_risk_assessment_plan,
)


def test_vendor_risk_assessment_plan_baseline_output() -> None:
    plan = generate_vendor_risk_assessment_plan(
        {
            "vendor_name": "Acme Analytics",
            "product": "Usage Metrics",
            "business_owner": "Product Ops",
            "criticality": "standard",
            "data_categories": ["product telemetry"],
            "security_evidence": ["SOC 2 Type II"],
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["vendor_inventory"]["vendor_name"] == "Acme Analytics"
    assert plan["criticality"] == "standard"
    assert plan["risk_rating"] == "low"
    assert plan["review_cadence"] == "annual"
    assert plan["approval_gates"][2]["required"] is False
    assert "SOC 2 Type II" in plan["security_evidence"]


def test_vendor_risk_assessment_plan_high_risk_vendor_escalates_controls() -> None:
    plan = generate_vendor_risk_assessment_plan(
        {
            "vendor": "HealthFlow",
            "product": "Patient Messaging",
            "criticality": "critical",
            "data_categories": ["personal data", "health data"],
            "regulations": ["HIPAA"],
            "risk_owner": "GRC",
        }
    )

    assert plan["data_access"]["sensitive_data"] is True
    assert plan["data_access"]["regulated_context"] is True
    assert plan["risk_rating"] == "high"
    assert plan["review_cadence"] == "quarterly"
    assert plan["approval_gates"][2] == {
        "gate": "executive_risk_acceptance",
        "owner": "GRC",
        "required": True,
    }
    assert any("risk committee" in control for control in plan["contractual_controls"])
    assert any("compensating controls" in item["action"] for item in plan["remediation_actions"])
