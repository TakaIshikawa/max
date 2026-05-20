from __future__ import annotations

import json

from max.spec import generate_support_coverage_gap_plan as exported_generator
from max.spec.support_coverage_gap_plan import KIND, SCHEMA_VERSION, generate_support_coverage_gap_plan


def test_support_coverage_gap_plan_uses_region_hours_and_escalation_hints() -> None:
    plan = generate_support_coverage_gap_plan(
        {
            "metadata": {
                "support_coverage_gap": {
                    "regions": [{"region": "APAC", "support_hours": "09:00-17:00 JST", "tier_owner": "tokyo-support"}],
                    "unsupported_scenarios": ["weekend launch"],
                    "escalation_contacts": ["support-director"],
                }
            }
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["coverage_windows"][0]["region"] == "APAC"
    assert plan["coverage_windows"][0]["tier_owner"] == "tokyo-support"
    assert plan["unsupported_scenarios"][0]["scenario"] == "weekend launch"
    assert plan["escalation_paths"][0]["contact"] == "support-director"
    assert exported_generator({})["kind"] == KIND


def test_support_coverage_gap_plan_defaults_are_stable_and_json_serializable() -> None:
    first = generate_support_coverage_gap_plan({})
    second = generate_support_coverage_gap_plan({})

    assert first == second
    assert first["coverage_windows"][0]["support_hours"] == "business hours"
    assert first["readiness_checks"]
    assert json.loads(json.dumps(first))["kind"] == KIND
