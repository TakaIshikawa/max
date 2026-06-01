from __future__ import annotations

from max.spec.profile_constraint_remediation_plan import generate_profile_constraint_remediation_plan


def test_profile_constraint_remediation_plan_orders_blocking_before_advisory() -> None:
    plan = generate_profile_constraint_remediation_plan(
        {"id": "p1", "owner": "ops"},
        [
            {"id": "v2", "constraint": "optional-source", "severity": "advisory"},
            {"id": "v1", "constraint": "required-role", "severity": "critical"},
        ],
    )

    assert [row["type"] for row in plan["remediation_tasks"]] == ["blocking", "advisory"]
    assert plan["remediation_tasks"][0]["owner"] == "ops"


def test_profile_constraint_remediation_plan_includes_target_date() -> None:
    plan = generate_profile_constraint_remediation_plan({"id": "p1"}, [{"id": "v1", "constraint": "coverage"}], target_date="2026-07-01")

    assert plan["summary"]["target_date"] == "2026-07-01"
    assert plan["remediation_tasks"][0]["target_date"] == "2026-07-01"


def test_profile_constraint_remediation_plan_handles_missing_profile() -> None:
    plan = generate_profile_constraint_remediation_plan(None, [{"id": "v1", "constraint": "coverage"}])

    assert plan["profile"]["status"] == "missing"
    assert plan["profile"]["profile_id"] == "missing_profile"


def test_profile_constraint_remediation_plan_adds_validation_check_for_each_task_and_sorts() -> None:
    plan = generate_profile_constraint_remediation_plan(
        {"id": "p1"},
        [
            {"id": "v3", "constraint": "z-advisory", "severity": "low"},
            {"id": "v2", "constraint": "b-blocking", "blocking": True},
            {"id": "v1", "constraint": "a-blocking", "severity": "high"},
        ],
    )

    assert [row["constraint"] for row in plan["remediation_tasks"]] == ["a-blocking", "b-blocking", "z-advisory"]
    assert [row["constraint"] for row in plan["validation_checks"]] == ["a-blocking", "b-blocking", "z-advisory"]
