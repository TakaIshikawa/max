from __future__ import annotations

from max.spec import generate_event_schema_evolution_plan


def test_event_schema_evolution_plan_orders_consumers() -> None:
    plan = generate_event_schema_evolution_plan({"metadata": {"event_schema_evolution": {"event": "OrderPlaced", "consumers": ["warehouse", "billing"], "producers": ["checkout"], "compatibility_mode": "dual-read"}}})

    assert plan["summary"]["event"] == "OrderPlaced"
    assert plan["compatibility"]["mode"] == "dual-read"
    assert [row["name"] for row in plan["consumer_impact"]] == ["billing", "warehouse"]
    assert plan["producer_impact"][0]["name"] == "checkout"


def test_event_schema_evolution_plan_sparse_defaults() -> None:
    plan = generate_event_schema_evolution_plan({})

    assert plan["rollout_phases"]
    assert plan["replay_strategy"]
    assert plan["deprecation_timeline"]
