from __future__ import annotations

import json

from max.spec import generate_operational_dependency_sunset_plan


def test_operational_dependency_sunset_plan_sorts_deadlines_and_consumers() -> None:
    plan = generate_operational_dependency_sunset_plan(
        _spec(
            "operational_dependency_sunset",
            {
                "dependencies": [
                    {"dependency": "Queue B", "severity": "low", "deadline_status": "ready"},
                    {"dependency": "Tool A", "severity": "high", "deadline_status": "overdue"},
                ],
                "consumers": ["Support", "Billing"],
                "replacement_path": ["new runbook"],
                "risk_controls": ["dual run"],
                "owner_handoffs": ["ops handoff"],
                "communications": ["consumer notice"],
                "rollback": ["restore old queue"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.operational_dependency_sunset_plan.v1"
    assert [item["name"] for item in plan["dependency_sunsets"]] == ["Tool A", "Queue B"]
    assert [item["name"] for item in plan["consumers"]] == ["Billing", "Support"]
    assert plan["rollback_criteria"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"replacement_paths", "risk_controls", "owner_handoffs", "communications"}
    assert json.loads(json.dumps(plan)) == plan


def test_operational_dependency_sunset_plan_defaults_sparse_input() -> None:
    plan = generate_operational_dependency_sunset_plan({})

    assert plan["dependency_sunsets"][0]["owner"] == "operations_owner"
    assert plan["rollback_criteria"][0]["name"] == "dependency rollback path"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["dep-1"]}}
