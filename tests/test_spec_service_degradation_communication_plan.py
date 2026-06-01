from __future__ import annotations

import pytest

from max.spec.service_degradation_communication_plan import generate_service_degradation_communication_plan


def test_service_degradation_communication_plan_contains_communication_workflow() -> None:
    plan = generate_service_degradation_communication_plan(_spec("high", "15 minutes"))

    assert plan["summary"]["service_name"] == "search api"
    assert set(plan) >= {"initial_notice", "update_schedule", "internal_coordination", "resolution_notice", "post_resolution_follow_up"}
    assert [item["name"] for item in plan["update_schedule"]] == ["email", "status page"]
    assert plan["post_resolution_follow_up"][0]["timing"] == "within 1 business day"


def test_service_degradation_communication_plan_uses_severity_specific_follow_up() -> None:
    plan = generate_service_degradation_communication_plan(_spec("medium", "1 hour"))

    assert plan["summary"]["update_cadence"] == "1 hour"
    assert plan["post_resolution_follow_up"][0]["timing"] == "within 3 business days"


@pytest.mark.parametrize(
    "field,match",
    [
        ("service_name", "service name"),
        ("severity", "severity"),
        ("affected_customers", "affected customers"),
        ("message_channels", "message channels"),
        ("update_cadence", "update cadence"),
    ],
)
def test_service_degradation_communication_plan_validates_required_inputs(field: str, match: str) -> None:
    hints = dict(_spec("high", "15 minutes")["metadata"]["service_degradation_communication"])
    hints[field] = []

    with pytest.raises(ValueError, match=match):
        generate_service_degradation_communication_plan({"metadata": {"service_degradation_communication": hints}})


def _spec(severity: str, cadence: str) -> dict:
    return {
        "metadata": {
            "service_degradation_communication": {
                "service_name": "search api",
                "severity": severity,
                "affected_customers": ["enterprise", "self serve"],
                "status_page_owner": "incident comms",
                "message_channels": ["status page", "email"],
                "update_cadence": cadence,
                "resolution_criteria": "latency below SLO for 30 minutes",
            }
        }
    }
