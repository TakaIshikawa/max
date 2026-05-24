from __future__ import annotations

from max.spec.data_minimization_exception_plan import (
    KIND,
    generate_data_minimization_exception_plan,
)


def test_data_minimization_exception_plan_contains_required_sections() -> None:
    plan = generate_data_minimization_exception_plan(
        {
            "id": "spec-1",
            "title": "Expanded telemetry",
            "metadata": {
                "data_minimization_exception": {
                    "exception_scope": [{"project": "analytics", "dataset": "events"}],
                    "impacted_data_classes": ["usage telemetry"],
                    "approvers": ["privacy"],
                }
            },
            "evidence": [{"id": "ev1"}],
        }
    )

    assert plan["kind"] == KIND
    assert plan["summary"]["exception_scope_count"] == 1
    assert plan["exception_scope"][0]["name"] == "analytics"
    assert plan["impacted_data_classes"]
    assert plan["compensating_controls"]
    assert plan["expiry"]
    assert plan["approval"]
    assert plan["deletion_follow_up"]


def test_data_minimization_exception_plan_defaults() -> None:
    plan = generate_data_minimization_exception_plan({})

    assert plan["exception_scope"][0]["name"] == "temporary expanded collection scope"
    assert plan["evidence_references"] == []
