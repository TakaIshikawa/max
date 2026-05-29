from __future__ import annotations

import json

from max.spec.llm_vendor_incident_communication_plan import (
    generate_llm_vendor_incident_communication_plan,
)


def test_llm_vendor_incident_communication_plan_captures_custom_incident_workflow() -> None:
    plan = generate_llm_vendor_incident_communication_plan(
        _spec(
            {
                "incidents": [
                    {
                        "provider": "provider-x",
                        "summary": "policy change broke evaluation calls",
                        "severity": "high",
                    }
                ],
                "affected_stages": ["evaluation", "batch synthesis"],
                "customer_impact": [{"audience": "enterprise admins", "impact": "delayed reports"}],
                "message_owners": [{"owner": "support lead", "role": "customer comms"}],
                "timelines": [{"milestone": "first update", "deadline": "30 minutes"}],
                "escalation_paths": [{"channel": "#incident", "recipient": "exec sponsor"}],
                "customer_notification_steps": [
                    {"audience": "affected customers", "channel": "status page"}
                ],
                "closure_criteria": ["impact review complete"],
            }
        )
    )

    assert plan["schema_version"] == "max.spec.llm_vendor_incident_communication_plan.v1"
    assert plan["summary"]["severity"] == "high"
    assert plan["incident_summary"][0]["provider"] == "provider-x"
    assert plan["affected_stages"][0]["name"] == "batch synthesis"
    assert plan["customer_impact"][0]["audience"] == "enterprise admins"
    assert plan["message_owners"][0]["role"] == "customer comms"
    assert plan["timelines"][0]["deadline"] == "30 minutes"
    assert plan["escalation_paths"][0]["channel"] == "#incident"
    assert plan["customer_notification_steps"][0]["channel"] == "status page"
    assert json.loads(json.dumps(plan)) == plan


def test_llm_vendor_incident_communication_plan_defaults_high_severity_escalation() -> None:
    plan = generate_llm_vendor_incident_communication_plan(
        _spec({"provider": "provider-y", "severity": "critical"})
    )

    assert plan["incident_summary"][0]["provider"] == "provider-y"
    assert plan["summary"]["severity"] == "critical"
    assert "executive sponsor" in plan["escalation_paths"][0]["name"]
    assert "customer notification" in plan["customer_notification_steps"][0]["name"]
    assert "impact review" in plan["closure_criteria"][0]["name"]
    assert set(plan) >= {
        "affected_stages",
        "customer_impact",
        "message_owners",
        "timelines",
        "escalation_paths",
        "customer_notification_steps",
        "closure_criteria",
    }


def _spec(hints: dict) -> dict:
    return {
        "metadata": {"llm_vendor_incident_communication": hints},
        "evidence": {"signal_ids": ["lv-1"]},
    }
