from __future__ import annotations

from max.spec.security_incident_tabletop_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_security_incident_tabletop_plan,
)


def test_security_incident_tabletop_plan_default_incident() -> None:
    plan = generate_security_incident_tabletop_plan({})

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["scenario"]["name"] == "Suspected credential compromise"
    assert plan["scenario"]["severity"] == "sev2"
    assert plan["roles"][0]["role"] == "incident_commander"
    assert len(plan["inject_timeline"]) == 5
    assert "incident bridge" in plan["communications"]["channels"]
    assert plan["communications"]["customer_notification_target"] == "after incident commander approval"
    assert any("evidence preservation" in item for item in plan["success_criteria"])
    assert plan["follow_up_actions"][0]["due"] == "2 business days"


def test_security_incident_tabletop_plan_regulated_customer_incident_strengthens_requirements() -> None:
    plan = generate_security_incident_tabletop_plan(
        {
            "scenario": "Customer personal data exposure through compromised support token",
            "severity": "critical",
            "regulated": True,
            "regulations": ["GDPR"],
            "customer_impacting": True,
            "legal_owner": "Privacy Counsel",
            "channels": ["Zoom bridge", "security-war-room", "customer-status-draft"],
        }
    )

    assert plan["scenario"]["regulated_context"] is True
    assert plan["scenario"]["customer_impacting"] is True
    assert plan["communications"]["customer_notification_target"] == "within 24 hours"
    assert plan["communications"]["executive_update"] == "every 30 minutes during exercise"
    assert plan["roles"][3] == {
        "role": "legal_privacy_reviewer",
        "owner": "Privacy Counsel",
        "required": True,
    }
    assert any("forensic preservation" in item for item in plan["evidence_collection"])
    assert any("customer notification decision" in item for item in plan["evidence_collection"])
