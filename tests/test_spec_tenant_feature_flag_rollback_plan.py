from __future__ import annotations

from max.spec.tenant_feature_flag_rollback_plan import generate_tenant_feature_flag_rollback_plan


def test_tenant_feature_flag_rollback_high_risk_first_and_sections() -> None:
    plan = generate_tenant_feature_flag_rollback_plan({"metadata": {"tenant_feature_flag_rollback": {"tenants": [{"tenant": "small", "risk": "low", "flag_owner": "ops"}, {"tenant": "enterprise", "risk": "high", "flag_owner": "ops"}]}}})
    assert [row["name"] for row in plan["tenant_groups"]] == ["enterprise", "small"]
    assert plan["blast_radius"] and plan["flag_state_inventory"] and plan["validation_checks"] and plan["customer_communication"]


def test_tenant_feature_flag_rollback_flags_missing_owner() -> None:
    plan = generate_tenant_feature_flag_rollback_plan({"metadata": {"tenant_feature_flag_rollback": {"segments": [{"segment": "regulated", "risk": "high"}]}}})
    assert "Missing flag owner" in plan["risk_flags"][0]["description"]


def test_tenant_feature_flag_rollback_empty_tenants_bootstraps() -> None:
    plan = generate_tenant_feature_flag_rollback_plan({})
    assert plan["tenant_groups"][0]["flag_owner"] == "missing"
