from __future__ import annotations

from max.spec import generate_tenant_region_migration_plan


def test_tenant_region_migration_plan_renders_migration_sections() -> None:
    plan = generate_tenant_region_migration_plan(
        {
            "metadata": {
                "tenant_region_migration": {
                    "tenants": [{"tenant": "acme", "source_region": "us-east-1", "target_region": "eu-west-1"}],
                    "replication": ["snapshot and checksum"],
                    "downtime_window": [{"window": "2026-07-01 01:00Z"}],
                    "compliance_checks": ["DPA region check"],
                    "customer_communication": ["migration notice"],
                    "rollback": ["restore source routing"],
                    "validation": ["data parity"],
                }
            }
        }
    )

    assert plan["migration_scope"][0]["name"] == "acme"
    assert set(plan) >= {"region_scope", "tenant_eligibility", "data_replication_plan", "downtime_window", "compliance_checks", "customer_communication", "rollback", "post_migration_validation"}


def test_tenant_region_migration_plan_defaults_sparse_input() -> None:
    plan = generate_tenant_region_migration_plan({})

    assert plan["migration_scope"][0]["owner"] == "migration_owner"
    assert plan["downtime_window"][0]["name"] == "downtime window not recorded"
