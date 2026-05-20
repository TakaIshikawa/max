from __future__ import annotations

import json

from max.spec import generate_customer_impact_assessment_plan as exported_generator
from max.spec.customer_impact_assessment_plan import KIND, SCHEMA_VERSION, generate_customer_impact_assessment_plan


def test_customer_impact_assessment_plan_uses_segments_scenarios_and_mitigation_owner() -> None:
    plan = generate_customer_impact_assessment_plan(
        {
            "project": {"specific_user": "admins"},
            "metadata": {
                "customer_impact_assessment": {
                    "customer_visible": True,
                    "segments": [{"name": "Enterprise admins", "owner": "cs", "impact": "settings delay"}],
                    "scenarios": [{"scenario": "settings unavailable", "severity": "high", "owner": "support"}],
                    "mitigation_owner": "support",
                }
            },
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["summary"]["customer_visible"] is True
    assert plan["impacted_segments"][0]["name"] == "Enterprise admins"
    assert plan["impact_scenarios"][0]["severity"] == "high"
    assert plan["mitigations"][0]["owner"] == "support"
    assert exported_generator({})["kind"] == KIND


def test_customer_impact_assessment_plan_sparse_defaults_are_stable_and_json_serializable() -> None:
    first = generate_customer_impact_assessment_plan({"project": {"specific_user": "operators"}})
    second = generate_customer_impact_assessment_plan({"project": {"specific_user": "operators"}})

    assert first == second
    assert first["impacted_segments"][0]["name"] == "operators"
    assert first["validation_checks"]
    assert json.loads(json.dumps(first))["kind"] == KIND
