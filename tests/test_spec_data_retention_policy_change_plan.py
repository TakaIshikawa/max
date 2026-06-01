from __future__ import annotations

import pytest

from max.spec.data_retention_policy_change_plan import generate_data_retention_policy_change_plan


def test_data_retention_policy_change_plan_handles_shorter_retention() -> None:
    plan = generate_data_retention_policy_change_plan(_spec("2 years", "90 days"))

    assert plan["summary"]["change_type"] == "shorter"
    assert set(plan) >= {"impact_analysis", "migration_tasks", "deletion_verification", "stakeholder_communication", "rollback_criteria"}
    assert [item["name"] for item in plan["migration_tasks"]] == ["archive", "warehouse"]
    assert all(item["required_when"] == "shorter retention" for item in plan["deletion_verification"])


def test_data_retention_policy_change_plan_handles_longer_retention() -> None:
    plan = generate_data_retention_policy_change_plan(_spec("90 days", "2 years"))

    assert plan["summary"]["change_type"] == "longer"
    assert all(item["required_when"] == "policy reconciliation" for item in plan["deletion_verification"])


@pytest.mark.parametrize(
    "field,match",
    [
        ("dataset", "dataset"),
        ("current_retention", "current retention"),
        ("proposed_retention", "proposed retention"),
        ("legal_basis", "legal basis"),
        ("affected_systems", "affected systems"),
        ("owners", "owners"),
    ],
)
def test_data_retention_policy_change_plan_validates_required_inputs(field: str, match: str) -> None:
    hints = dict(_spec("1 year", "90 days")["metadata"]["data_retention_policy_change"])
    hints[field] = []

    with pytest.raises(ValueError, match=match):
        generate_data_retention_policy_change_plan({"metadata": {"data_retention_policy_change": hints}})


def _spec(current: str, proposed: str) -> dict:
    return {
        "metadata": {
            "data_retention_policy_change": {
                "dataset": "support transcripts",
                "current_retention": current,
                "proposed_retention": proposed,
                "legal_basis": "contractual support obligation",
                "affected_systems": ["warehouse", "archive"],
                "owners": ["privacy owner", "data owner"],
                "migration_deadline": "2026-10-01",
                "communication_channels": ["legal review", "customer notice"],
            }
        }
    }
