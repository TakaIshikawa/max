from __future__ import annotations

import json

import pytest

from max.spec import generate_data_residency_exception_plan


def test_data_residency_exception_plan_renders_required_workflow() -> None:
    plan = generate_data_residency_exception_plan(_spec())

    assert plan["schema_version"] == "max.spec.data_residency_exception_plan.v1"
    assert plan["exception_scope"][0]["region"] == "EU to US"
    assert plan["exception_scope"][0]["data_classes"] == ["analytics events", "support logs"]
    assert [item["name"] for item in plan["risk_controls"]] == ["field encryption", "transfer audit logging"]
    assert [item["name"] for item in plan["approval_workflow"]] == ["legal reviewer", "privacy approver"]
    assert [item["name"] for item in plan["monitoring_tasks"]] == ["customer impact review", "regional transfer dashboard"]
    assert [item["name"] for item in plan["expiry_review_checkpoints"]] == ["Renewal decision", "Closure verification"]
    assert json.loads(json.dumps(plan)) == plan


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("region", "region"),
        ("requesting_owner", "owner"),
        ("data_classes", "data_classes"),
        ("expiry_date", "expiry_date"),
        ("compensating_controls", "compensating_controls"),
        ("review_approvers", "review_approvers"),
    ],
)
def test_data_residency_exception_plan_rejects_missing_required_inputs(field: str, message: str) -> None:
    hints = dict(_spec()["metadata"]["data_residency_exception"])
    hints.pop(field)

    with pytest.raises(ValueError, match=message):
        generate_data_residency_exception_plan({"metadata": {"data_residency_exception": hints}})


def test_data_residency_exception_plan_is_deterministic() -> None:
    assert generate_data_residency_exception_plan(_spec()) == generate_data_residency_exception_plan(_spec())


def _spec() -> dict:
    return {
        "metadata": {
            "data_residency_exception": {
                "request": "EU support replay in US analytics stack",
                "region": "EU to US",
                "requesting_owner": "privacy lead",
                "data_classes": ["support logs", "analytics events", "support logs"],
                "expiry_date": "2026-06-30",
                "compensating_controls": ["transfer audit logging", "field encryption"],
                "review_approvers": ["privacy approver", "legal reviewer"],
                "monitoring": ["regional transfer dashboard", "customer impact review"],
            }
        },
        "evidence": {"insight_ids": ["dre-1"]},
    }
