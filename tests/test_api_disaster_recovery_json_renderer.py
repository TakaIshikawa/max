from __future__ import annotations

from max.api import disaster_recovery_plan_to_json
from max.spec.disaster_recovery import generate_disaster_recovery_plan


def test_disaster_recovery_renderer_serializes_plan_fields() -> None:
    plan = {
        "schema_version": "max.disaster_recovery_plan.v1",
        "kind": "max.disaster_recovery_plan",
        "summary": {
            "title": "Payment Service",
            "recovery_time_objective": "4 hours",
            "recovery_point_objective": "15 minutes",
        },
        "procedures": [{"id": "PROC-01", "name": "Restore database"}],
        "contacts": [{"name": "Incident Lead", "role": "commander"}],
        "escalation_paths": [{"level": 1, "owner": "platform"}],
        "scenarios": [{"id": "SCN-01", "name": "Regional outage"}],
    }

    payload = disaster_recovery_plan_to_json(plan)

    assert payload["kind"] == "max.api.disaster_recovery"
    assert payload["summary"]["title"] == "Payment Service"
    assert payload["objectives"] == {"rto": "4 hours", "rpo": "15 minutes"}
    assert payload["procedures"][0]["name"] == "Restore database"
    assert payload["contacts"][0]["role"] == "commander"
    assert payload["escalation_paths"][0]["owner"] == "platform"
    assert payload["metadata"]["procedure_count"] == 1


def test_disaster_recovery_renderer_accepts_generated_plan_shape() -> None:
    plan = generate_disaster_recovery_plan(
        {
            "schema_version": "max.tact_spec.v1",
            "project": {"title": "Generated Service"},
            "source": {"idea_id": "idea-1"},
        }
    )

    payload = disaster_recovery_plan_to_json(plan)

    assert payload["metadata"]["source_kind"] == "max.disaster_recovery_plan"
    assert payload["summary"]["title"] == "Generated Service"
    assert "rto" in payload["objectives"]
    assert "rpo" in payload["objectives"]
