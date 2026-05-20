from __future__ import annotations

import json

from max.spec import generate_support_tier_migration_plan


def test_support_tier_migration_plan_uses_hints() -> None:
    plan = generate_support_tier_migration_plan(
        _spec(
            "support_tier_migration",
            {
                "tier_changes": [
                    {"name": "Gold to Premium"},
                    {"name": "Gold to Premium"},
                    {"name": "Basic to Standard"},
                ],
                "customer_segments": ["enterprise", "startup", "enterprise"],
                "routing_updates": ["premium queue"],
                "entitlement_checks": ["SLA parity"],
                "staffing_actions": ["weekend coverage"],
                "communications": ["migration email"],
                "validation_checks": ["ticket routing smoke test"],
            },
        )
    )

    assert [item["name"] for item in plan["tier_changes"]] == [
        "Basic to Standard",
        "Gold to Premium",
    ]
    assert [item["name"] for item in plan["impacted_customers"]] == ["enterprise", "startup"]
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_support_tier_migration_plan_defaults_sparse_input() -> None:
    plan = generate_support_tier_migration_plan({})

    assert plan["tier_changes"][0]["name"] == "standard support tier update"
    assert plan["impacted_customers"][0]["name"] == "primary user"
    assert set(plan) >= {
        "routing_updates",
        "entitlement_checks",
        "staffing_actions",
        "communications",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
