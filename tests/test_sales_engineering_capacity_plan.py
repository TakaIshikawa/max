from __future__ import annotations

from unittest.mock import MagicMock

from max.exports import build_sales_engineering_capacity_plan_export
from max.exports.sales_engineering_capacity_plan import render_sales_engineering_capacity_plan_markdown


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_capacity_plan_includes_buckets_gap_risk_and_recommendations() -> None:
    report = build_sales_engineering_capacity_plan_export(_store([
        _unit("a", {"implementation_complexity": "enterprise complex", "integrations": ["sso", "sap"], "weekly_capacity_hours": 40}),
        _unit("b", {"implementation_complexity": "medium", "estimated_effort_hours": 12}),
    ]))

    assert report["summary"]["total_effort_hours"] == 52
    assert report["summary"]["capacity_gap_hours"] == 12
    assert report["summary"]["risk_level"] == "medium"
    assert report["demand_buckets"][0]["bucket"] == "enterprise_complex"
    assert report["staffing_recommendations"]


def test_zero_capacity_and_zero_demand_are_deterministic() -> None:
    demand = build_sales_engineering_capacity_plan_export(_store([_unit("a", {"implementation_complexity": "high"})]))
    empty = build_sales_engineering_capacity_plan_export(_store([]))

    assert demand["summary"]["weekly_capacity_hours"] == 0
    assert demand["summary"]["risk_level"] == "high"
    assert empty["summary"]["risk_level"] == "low"
    assert "No sales engineering demand" in render_sales_engineering_capacity_plan_markdown(empty)
