from __future__ import annotations

from max.spec import generate_privacy_deletion_workflow_plan


def test_privacy_deletion_workflow_plan_rich_inputs() -> None:
    plan = generate_privacy_deletion_workflow_plan({"metadata": {"privacy_deletion_workflow": {"workflow": "account deletion", "data_inventory": ["profile"], "processors": ["crm"], "exceptions": ["legal hold"]}}})

    assert plan["summary"]["workflow"] == "account deletion"
    assert plan["data_inventory"][0]["name"] == "profile"
    assert plan["processor_propagation"][0]["name"] == "crm"
    assert plan["exception_handling"][0]["name"] == "legal hold"


def test_privacy_deletion_workflow_plan_sparse_defaults() -> None:
    plan = generate_privacy_deletion_workflow_plan({})

    assert plan["systems_of_record"]
    assert plan["verification_evidence"]
    assert plan["audit_retention"]
