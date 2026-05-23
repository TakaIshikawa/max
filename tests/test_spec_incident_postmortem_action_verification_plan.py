from max.spec import generate_incident_postmortem_action_verification_plan


def test_incident_postmortem_action_plan_uses_overdue_metadata():
    plan = generate_incident_postmortem_action_verification_plan(
        {"metadata": {"incident_postmortem_action_verification": {"action_items": [{"action": "Patch failover", "owner": "SRE", "status": "overdue"}]}}}
    )

    assert plan["action_items"][0]["id"] == "IPA1"
    assert plan["action_items"][0]["name"] == "Patch failover"
    assert plan["action_items"][0]["owner"] == "SRE"
    assert plan["action_items"][0]["status"] == "overdue"


def test_incident_postmortem_action_plan_defaults_verification_behavior():
    plan = generate_incident_postmortem_action_verification_plan({})

    assert plan["verification_steps"]
    assert "completed remediation" in plan["verification_steps"][0]["description"]
    assert plan["escalation_workflow"]
