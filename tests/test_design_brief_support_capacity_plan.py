from __future__ import annotations

import json

from max.analysis import generate_design_brief_support_capacity_plan as exported_generate
from max.analysis.design_brief_support_capacity_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_support_capacity_plan,
)


def test_support_capacity_plan_calculates_coverage_by_tier() -> None:
    brief = {
        "metadata": {
            "support_capacity_plan": {
                "escalation_load": "10 escalations/week",
                "support_tiers": [
                    {"tier": "Tier 2", "required_staff": 3, "assigned_staff": 4, "ticket_volume": 40, "owner": "support", "evidence": ["forecast"]},
                    {"tier": "Tier 1", "required_staff": 5, "assigned_staff": 5, "ticket_volume": 120, "owner": "support", "evidence": ["history"]},
                ],
            }
        }
    }

    plan = generate_design_brief_support_capacity_plan(brief)

    assert plan == generate_design_brief_support_capacity_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [row["tier"] for row in plan["capacity_by_tier"]] == ["Tier 1", "Tier 2"]
    assert [row["coverage_delta"] for row in plan["capacity_by_tier"]] == [0, 1]
    assert plan["summary"]["recommendation_status"] == "ready"
    assert exported_generate({})["kind"] == KIND


def test_support_capacity_plan_reports_understaffing_and_missing_escalation_load() -> None:
    plan = generate_design_brief_support_capacity_plan(
        {"support_capacity_plan": {"tiers": [{"name": "Tier 1", "required": 3, "assigned": 1}]}}
    )

    assert plan["summary"]["recommendation_status"] == "blocked"
    assert [gap["id"] for gap in plan["capacity_gaps"]] == [
        "missing_escalation_load",
        "tier_1_understaffed",
    ]
