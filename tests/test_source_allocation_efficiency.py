from __future__ import annotations

import json

from max.exports.source_allocation_efficiency import (
    KIND,
    build_source_allocation_efficiency_report,
    render_source_allocation_efficiency_json,
)


def test_source_allocation_efficiency_calculates_rows_and_sorts() -> None:
    report = build_source_allocation_efficiency_report(
        [
            {"source": "news", "allocated_budget": 100, "consumed_budget": 50, "signal_count": 25, "accepted_signal_count": 10, "insight_count": 5, "previous_weight": 0.2, "current_weight": 0.4},
            {"source": "social", "allocated_budget": 100, "consumed_budget": 125, "signal_count": 25, "accepted_signal_count": 5, "insight_count": 1, "failure_count": 2},
            {"source": "docs", "allocated_budget": 80, "consumed_budget": 10, "signal_count": 10, "accepted_signal_count": 5, "insight_count": 2},
        ]
    )

    assert report["kind"] == KIND
    assert [row["source"] for row in report["source_efficiency"]] == ["docs", "news", "social"]
    assert report["source_efficiency"][0]["yield_per_budget"] == 1.0
    assert report["summary"]["underused_count"] == 1
    assert report["underused_allocations"][0]["source"] == "docs"
    assert report["overrun_allocations"][0]["source"] == "social"
    assert report["weight_adjustments"][0]["source"] == "news"
    assert json.loads(render_source_allocation_efficiency_json(report))["summary"]["source_count"] == 3


def test_source_allocation_efficiency_handles_zero_missing_budgets() -> None:
    report = build_source_allocation_efficiency_report([{}])

    row = report["source_efficiency"][0]
    assert row["source"] == "Unknown source"
    assert row["yield_per_budget"] == 0.0
    assert row["acceptance_rate"] == 0.0
    assert report["underused_allocations"] == []
    assert report["overrun_allocations"] == []
