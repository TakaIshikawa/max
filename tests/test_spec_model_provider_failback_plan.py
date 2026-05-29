from __future__ import annotations

from max.spec import generate_model_provider_failback_plan


def test_model_provider_failback_plan_normalizes_traffic_ramp() -> None:
    plan = generate_model_provider_failback_plan({"metadata": {"model_provider_failback": {"primary_provider_health": "healthy", "traffic_ramp": ["50%", "10", 100, "10"]}}})
    assert [row["percentage"] for row in plan["traffic_ramp"]] == [10, 50, 100]
    assert plan["summary"]["primary_provider_health"] == "healthy"
    assert plan["quality_regression_checks"]


def test_model_provider_failback_plan_degraded_and_sparse_payloads() -> None:
    degraded = generate_model_provider_failback_plan({"metadata": {"model_provider_failback": {"health_status": "degraded"}}})
    assert degraded["summary"]["primary_provider_health"] == "degraded"
    sparse = generate_model_provider_failback_plan({})
    assert sparse["traffic_ramp"]
    assert sparse["rollback_triggers"]
