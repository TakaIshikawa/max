from __future__ import annotations

from max.spec import generate_schema_contract_migration_plan


def test_schema_contract_migration_plan_rich_sections() -> None:
    plan = generate_schema_contract_migration_plan({"metadata": {"schema_contract_migration": {"current_contract": "orders.v1", "target_contract": "orders.v2", "consumers": ["billing"], "compatibility_risks": ["required field"]}}})

    assert plan["current_contract"]["name"] == "orders.v1"
    assert plan["target_contract"]["name"] == "orders.v2"
    assert plan["compatibility_risks"][0]["name"] == "required field"
    assert plan["consumer_validation"][0]["name"] == "billing"


def test_schema_contract_migration_plan_sparse_defaults() -> None:
    plan = generate_schema_contract_migration_plan({})

    assert plan["migration_steps"]
    assert plan["rollback_strategy"]
    assert plan["acceptance_checks"]
