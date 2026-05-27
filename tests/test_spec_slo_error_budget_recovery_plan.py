from __future__ import annotations

from max.spec.slo_error_budget_recovery_plan import generate_slo_error_budget_recovery_plan


def test_slo_error_budget_recovery_plan_marks_exhausted_budget() -> None:
    plan = generate_slo_error_budget_recovery_plan({"metadata": {"slo_error_budget_recovery": {"services": [{"service": "api", "error_budget_remaining": 0, "burn_rate": 3}]}}})

    assert plan["service_inventory"][0]["budget_status"] == "exhausted"
    assert "freeze" in plan["service_inventory"][0]["recommended_action"]


def test_slo_error_budget_recovery_plan_missing_target_creates_watch() -> None:
    plan = generate_slo_error_budget_recovery_plan({"metadata": {"slo_error_budget_recovery": {"services": [{"service": "api", "error_budget_remaining": 50, "burn_rate": 0.2}]}}})

    assert plan["service_inventory"][0]["slo_target"] == "target missing"
    assert plan["service_inventory"][0]["budget_status"] == "watch"


def test_slo_error_budget_recovery_plan_sorts_by_severity_then_name() -> None:
    plan = generate_slo_error_budget_recovery_plan({"metadata": {"slo_error_budget_recovery": {"services": [{"service": "zeta", "error_budget_remaining": 20, "burn_rate": 2.5, "slo_target": "99.9"}, {"service": "alpha", "error_budget_remaining": 20, "burn_rate": 2.5, "slo_target": "99.9"}, {"service": "core", "error_budget_remaining": 0, "slo_target": "99.9"}]}}})

    assert [row["service"] for row in plan["service_inventory"]] == ["core", "alpha", "zeta"]


def test_slo_error_budget_recovery_plan_healthy_defaults() -> None:
    plan = generate_slo_error_budget_recovery_plan({})

    assert plan["service_inventory"][0]["budget_status"] == "healthy"
    assert "monitoring" in plan["service_inventory"][0]["recommended_action"]
