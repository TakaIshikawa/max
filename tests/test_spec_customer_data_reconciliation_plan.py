from __future__ import annotations

from max.spec.customer_data_reconciliation_plan import generate_customer_data_reconciliation_plan


def test_customer_data_reconciliation_orders_mismatches_by_severity() -> None:
    plan = generate_customer_data_reconciliation_plan({"metadata": {"customer_data_reconciliation": {"mismatches": [{"id": "b", "severity": "low"}, {"id": "a", "severity": "high"}]}}})
    assert [row["name"] for row in plan["mismatch_taxonomy"]] == ["a", "b"]
    assert "Customer notice required" in plan["customer_notice_triggers"][0]["description"]


def test_customer_data_reconciliation_flags_conflicting_source_of_truth() -> None:
    plan = generate_customer_data_reconciliation_plan({"metadata": {"customer_data_reconciliation": {"source_mapping": [{"field": "email", "system": "crm"}, {"field": "email", "system": "billing"}], "mismatch_inventory": [{"name": "email", "severity": "medium"}]}}})
    assert plan["risk_flags"][0]["name"] == "conflicting source of truth"


def test_customer_data_reconciliation_empty_mismatches_defaults() -> None:
    plan = generate_customer_data_reconciliation_plan({})
    assert plan["mismatch_taxonomy"]
    assert plan["audit_evidence"]
