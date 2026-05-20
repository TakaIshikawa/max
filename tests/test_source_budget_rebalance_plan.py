from __future__ import annotations

from max.analysis.source_budget_rebalance_plan import (
    build_source_budget_rebalance_plan,
    render_source_budget_rebalance_plan_markdown,
)


def test_source_budget_rebalance_plan_recommends_all_directions() -> None:
    plan = build_source_budget_rebalance_plan(
        [
            {
                "source": "high_yield",
                "current_budget": 1000,
                "observed_yield": 300,
                "cost": 100,
                "error_rate": 0.05,
                "strategic_weight": 0.8,
            },
            {
                "source": "broken_low_value",
                "current_budget": 500,
                "observed_yield": 25,
                "cost": 100,
                "error_rate": 0.6,
                "strategic_weight": 0.2,
            },
            {
                "source": "noisy_strategic",
                "current_budget": 700,
                "observed_yield": 120,
                "cost": 100,
                "error_rate": 0.35,
                "strategic_weight": 0.9,
            },
            {
                "source": "steady_reference",
                "current_budget": 300,
                "observed_yield": 120,
                "cost": 100,
                "error_rate": 0.1,
                "strategic_weight": 0.4,
            },
        ]
    )

    assert plan["schema_version"] == "max.source_budget_rebalance_plan.v1"
    assert plan["kind"] == "max.source_budget_rebalance_plan"
    assert plan["summary"] == {
        "source_count": 4,
        "increase_count": 1,
        "hold_count": 1,
        "reduce_count": 1,
        "pause_count": 1,
    }
    rows = {row["source"]: row for row in plan["rebalance_rows"]}
    assert rows["high_yield"]["recommendation"] == "increase"
    assert rows["broken_low_value"]["recommendation"] == "pause"
    assert rows["noisy_strategic"]["recommendation"] == "reduce"
    assert rows["steady_reference"]["recommendation"] == "hold"
    assert rows["high_yield"]["yield_per_cost"] == 3.0
    assert "cap increases" in rows["high_yield"]["guardrail_note"]


def test_source_budget_rebalance_plan_sorts_by_direction_and_priority() -> None:
    plan = build_source_budget_rebalance_plan(
        [
            {
                "source": "increase_lower",
                "current_budget": 100,
                "observed_yield": 210,
                "cost": 100,
                "error_rate": 0.05,
                "strategic_weight": 0.6,
            },
            {
                "source": "hold_strategic",
                "current_budget": 100,
                "observed_yield": 140,
                "cost": 100,
                "error_rate": 0.05,
                "strategic_weight": 0.9,
            },
            {
                "source": "increase_higher",
                "current_budget": 100,
                "observed_yield": 300,
                "cost": 100,
                "error_rate": 0.02,
                "strategic_weight": 0.9,
            },
        ]
    )

    assert [row["source"] for row in plan["rebalance_rows"]] == [
        "increase_higher",
        "increase_lower",
        "hold_strategic",
    ]


def test_source_budget_rebalance_plan_considers_error_rate_before_yield() -> None:
    plan = build_source_budget_rebalance_plan(
        [
            {
                "source": "high_yield_noisy",
                "current_budget": 100,
                "observed_yield": 500,
                "cost": 100,
                "error_rate": 0.5,
                "strategic_weight": 0.6,
            }
        ]
    )

    row = plan["rebalance_rows"][0]
    assert row["yield_per_cost"] == 5.0
    assert row["recommendation"] == "pause"
    assert row["guardrail_note"] == "resume only after error remediation and a clean sampling run"


def test_source_budget_rebalance_plan_markdown_is_deterministic() -> None:
    plan = build_source_budget_rebalance_plan(
        [
            {"source": "z source", "current_budget": 200, "observed_yield": 30, "cost": 100, "strategic_weight": 0.4},
            {
                "source": "a source",
                "current_budget": 400,
                "observed_yield": 250,
                "cost": 100,
                "error_rate": 0.04,
                "strategic_weight": 0.8,
            },
        ]
    )

    first = render_source_budget_rebalance_plan_markdown(plan)
    second = render_source_budget_rebalance_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Source Budget Rebalance Plan")
    assert first.index("### a source") < first.index("### z source")
    assert "## Source Recommendations" in first
    assert "- Current budget: 400.00" in first
    assert "- Recommended budget direction: increase" in first
    assert "- Reason:" in first
    assert "- Guardrail note:" in first
