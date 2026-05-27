from __future__ import annotations

from max.spec.incident_customer_notification_plan import generate_incident_customer_notification_plan


def test_incident_customer_notification_plan_maps_severity_to_timing() -> None:
    plan = generate_incident_customer_notification_plan({"metadata": {"incident_customer_notification": {"severity": "sev1"}}})

    assert plan["schema_version"] == "max.spec.incident_customer_notification_plan.v1"
    assert plan["timing_sla"] == "notify within 30 minutes, then hourly until mitigated"


def test_incident_customer_notification_plan_escalates_regulated_customers() -> None:
    plan = generate_incident_customer_notification_plan({"metadata": {"incident_customer_notification": {"segments": [{"segment": "bank customers", "customer_type": "regulated enterprise"}]}}})

    assert plan["audience_segments"][0]["approval_required"] is True
    assert plan["audience_segments"][0]["evidence_required"] is True
    assert "legal/privacy" in plan["audience_segments"][0]["evidence_needs"]


def test_incident_customer_notification_plan_defaults_empty_segments() -> None:
    plan = generate_incident_customer_notification_plan({"metadata": {"incident_customer_notification": {}}})

    assert plan["audience_segments"][0]["name"] == "all impacted customers"
    assert plan["audience_segments"][0]["customer_type"] == "standard"
