from __future__ import annotations

import pytest

from max.spec.incident_postmortem_action_plan import generate_incident_postmortem_action_plan


def test_incident_postmortem_action_plan_maps_actions_and_customer_follow_up() -> None:
    plan = generate_incident_postmortem_action_plan(_spec("sev1"))

    assert plan["summary"]["incident_id"] == "INC-42"
    assert [item["name"] for item in plan["root_cause_mapping"]] == ["missing alert", "unsafe deploy"]
    assert [item["name"] for item in plan["corrective_actions"]] == ["add deployment gate", "restore latency alert"]
    assert "executive review" in [item["name"] for item in plan["prevention_checks"]]
    assert set(plan) >= {"impact_summary", "customer_follow_up", "review_cadence"}


def test_incident_postmortem_action_plan_severity_specific_tasks() -> None:
    low = generate_incident_postmortem_action_plan(_spec("sev3"))

    assert "executive review" not in [item["name"] for item in low["prevention_checks"]]


@pytest.mark.parametrize("field,match", [("incident_id", "incident id"), ("severity", "severity"), ("root_causes", "root causes"), ("owners", "action owners")])
def test_incident_postmortem_action_plan_validates_required_fields(field: str, match: str) -> None:
    hints = dict(_spec("sev1")["metadata"]["incident_postmortem_action"])
    hints.pop(field)

    with pytest.raises(ValueError, match=match):
        generate_incident_postmortem_action_plan({"metadata": {"incident_postmortem_action": hints}})


def test_incident_postmortem_action_plan_is_deterministic() -> None:
    assert generate_incident_postmortem_action_plan(_spec("sev1")) == generate_incident_postmortem_action_plan(_spec("sev1"))


def _spec(severity: str) -> dict:
    return {
        "metadata": {
            "incident_postmortem_action": {
                "incident_id": "INC-42",
                "severity": severity,
                "timeline_summary": "latency regression lasted 32 minutes",
                "root_causes": ["unsafe deploy", "missing alert"],
                "owners": ["sre lead", "app owner"],
                "actions": ["restore latency alert", "add deployment gate"],
                "customer_impact": "delayed exports",
                "follow_up_review_date": "2026-07-15",
            }
        },
        "evidence": {"insight_ids": ["inc-1"]},
    }
