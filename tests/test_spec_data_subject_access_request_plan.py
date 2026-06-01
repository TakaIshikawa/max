from __future__ import annotations

import pytest

from max.spec.data_subject_access_request_plan import generate_data_subject_access_request_plan


def test_data_subject_access_request_plan_requires_request_and_subject_ids() -> None:
    with pytest.raises(ValueError, match="subject_id"):
        generate_data_subject_access_request_plan({"request_id": "dsar-1"}, [])

    with pytest.raises(ValueError, match="request_id"):
        generate_data_subject_access_request_plan({"subject_id": "sub-1"}, [])


def test_data_subject_access_request_plan_groups_systems_by_owner() -> None:
    plan = generate_data_subject_access_request_plan(
        {"request_id": "dsar-1", "subject_id": "sub-1"},
        [
            {"system": "billing", "owner": "finance", "data_categories": ["payment"]},
            {"system": "crm", "owner": "support", "data_categories": "email, notes"},
            {"system": "tickets", "owner": "support", "data_categories": ["messages"]},
        ],
    )

    assert plan["title"] == "DSAR Plan dsar-1"
    assert [(group["owner"], [row["system"] for row in group["systems"]]) for group in plan["systems_by_owner"]] == [
        ("finance", ["billing"]),
        ("support", ["crm", "tickets"]),
    ]
    assert plan["evidence_checklist"]


def test_data_subject_access_request_plan_derives_sla_deadline() -> None:
    plan = generate_data_subject_access_request_plan(
        {"request_id": "dsar-1", "subject_id": "sub-1", "received_on": "2026-06-01"},
        [],
        sla_days=45,
    )

    assert plan["summary"]["deadline"] == "2026-07-16"
    assert plan["milestones"][-1]["due"] == "2026-07-16"


def test_data_subject_access_request_plan_orders_tasks_deterministically() -> None:
    plan = generate_data_subject_access_request_plan(
        {"request_id": "dsar-1", "subject_id": "sub-1"},
        [
            {"system": "zeta", "owner": "ops"},
            {"system": "alpha", "owner": "ops"},
            {"system": "billing", "owner": "finance"},
        ],
    )

    system_tasks = [task for task in plan["tasks"] if task.get("system")]
    assert [task["system"] for task in system_tasks] == ["billing", "alpha", "zeta"]
    assert [task["phase"] for task in plan["tasks"]][-3:] == ["export_review", "delivery", "audit_evidence"]
