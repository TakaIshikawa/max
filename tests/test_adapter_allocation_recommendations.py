"""Tests for adapter allocation recommendation digests."""

from __future__ import annotations

import csv
import json
from io import StringIO
from types import MethodType

import pytest

from max.analysis.adapter_allocation_recommendations import (
    KIND,
    SCHEMA_VERSION,
    build_adapter_allocation_recommendations,
    render_adapter_allocation_recommendations,
)
from max.store.db import Store


def test_build_adapter_allocation_recommendations_ranks_actions(store: Store) -> None:
    _seed_allocation_runs(store)
    _stub_quality_stats(store)

    report = build_adapter_allocation_recommendations(store, limit=10, min_runs=1)
    repeated = build_adapter_allocation_recommendations(store, limit=10, min_runs=1)

    assert report == repeated
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert [row["adapter"] for row in report["recommendations"]] == [
        "broken_adapter",
        "low_util_adapter",
        "steady_adapter",
        "growth_adapter",
    ]
    assert report["allocation_bands"] == {
        "pause": ["broken_adapter"],
        "reduce": ["low_util_adapter"],
        "hold": ["steady_adapter"],
        "increase": ["growth_adapter"],
    }
    assert report["summary"]["adapter_count"] == 4

    rows = {row["adapter"]: row for row in report["recommendations"]}
    assert rows["broken_adapter"]["action"] == "pause"
    assert rows["broken_adapter"]["latest_error_state"] == {
        "status": "error",
        "error_message": "HTTP 500",
        "has_error": True,
    }
    assert rows["low_util_adapter"]["action"] == "reduce"
    assert rows["low_util_adapter"]["utilization_hit_rate"] == pytest.approx(0.05)
    assert rows["steady_adapter"]["action"] == "hold"
    assert rows["growth_adapter"]["action"] == "increase"
    assert any("Pause allocation" in action for action in report["next_actions"])
    assert any("Shift spare allocation" in action for action in report["next_actions"])


def test_adapter_allocation_recommendations_min_runs_filters(store: Store) -> None:
    _seed_allocation_runs(store)
    _stub_quality_stats(store)

    report = build_adapter_allocation_recommendations(store, limit=10, min_runs=3)

    assert [row["adapter"] for row in report["recommendations"]] == [
        "broken_adapter",
        "steady_adapter",
        "growth_adapter",
    ]
    assert report["summary"]["excluded_below_min_runs_count"] == 1


def test_adapter_allocation_recommendations_empty_store_returns_guidance(store: Store) -> None:
    report = build_adapter_allocation_recommendations(store)

    assert report["recommendations"] == []
    assert report["summary"]["run_count"] == 0
    assert report["next_actions"] == [
        "Run the pipeline with adapter metrics enabled, then synthesize signals before changing allocations."
    ]


def test_render_adapter_allocation_recommendations_json_markdown_csv_and_invalid_format(
    store: Store,
) -> None:
    _seed_allocation_runs(store)
    _stub_quality_stats(store)
    report = build_adapter_allocation_recommendations(store, limit=10, min_runs=1)

    assert json.loads(render_adapter_allocation_recommendations(report, fmt="json")) == report

    markdown = render_adapter_allocation_recommendations(report, fmt="markdown")
    assert markdown.startswith("# Adapter Allocation Recommendations")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert "## Recommendations" in markdown
    assert "| `broken_adapter` | pause |" in markdown
    assert "## Next Actions" in markdown

    rendered_csv = render_adapter_allocation_recommendations(report, fmt="csv")
    assert rendered_csv.splitlines()[0] == (
        "adapter_name,action,confidence,priority,run_count,success_rate,"
        "average_fetched_signals,utilization_hit_rate,latest_status,latest_error,recommendation"
    )
    rows = list(csv.DictReader(StringIO(rendered_csv)))
    assert [row["adapter_name"] for row in rows] == [
        "broken_adapter",
        "low_util_adapter",
        "steady_adapter",
        "growth_adapter",
    ]
    assert rows[0]["action"] == "pause"
    assert rows[0]["latest_error"] == "HTTP 500"
    assert rows[3]["action"] == "increase"

    with pytest.raises(ValueError, match="Unsupported adapter allocation recommendations format: yaml"):
        render_adapter_allocation_recommendations(report, fmt="yaml")


def test_adapter_allocation_recommendations_validates_arguments(store: Store) -> None:
    with pytest.raises(ValueError, match="limit must be at least 1"):
        build_adapter_allocation_recommendations(store, limit=0)
    with pytest.raises(ValueError, match="min_runs must be at least 1"):
        build_adapter_allocation_recommendations(store, min_runs=0)


def _seed_allocation_runs(store: Store) -> None:
    _insert_run(
        store,
        "run-allocation-001",
        "2026-05-01T00:00:00",
        {
            "growth_adapter": {"status": "ok", "signal_count": 5},
            "steady_adapter": {"status": "ok", "signal_count": 2},
            "broken_adapter": {"status": "error", "signal_count": 0, "error_message": "timeout"},
        },
    )
    _insert_run(
        store,
        "run-allocation-002",
        "2026-05-02T00:00:00",
        {
            "growth_adapter": {"status": "ok", "signal_count": 6},
            "steady_adapter": {"status": "ok", "signal_count": 2},
            "broken_adapter": {"status": "error", "signal_count": 0, "error_message": "timeout"},
            "low_util_adapter": {"status": "ok", "signal_count": 4},
        },
    )
    _insert_run(
        store,
        "run-allocation-003",
        "2026-05-03T00:00:00",
        {
            "growth_adapter": {"status": "ok", "signal_count": 7},
            "steady_adapter": {"status": "ok", "signal_count": 2},
            "broken_adapter": {"status": "error", "signal_count": 0, "error_message": "HTTP 500"},
        },
    )


def _insert_run(
    store: Store,
    run_id: str,
    started_at: str,
    adapter_metrics: dict[str, dict[str, object]],
) -> None:
    store.insert_pipeline_run(run_id, {"profile": "allocation"})
    store.update_pipeline_run(run_id, signals_fetched=10, adapter_metrics=adapter_metrics)
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store._commit()


def _stub_quality_stats(store: Store) -> None:
    def get_adapter_quality_stats(self: Store) -> dict[str, dict[str, float]]:
        return {
            "growth_adapter": {
                "total_signals": 18,
                "insight_hit_rate": 0.45,
                "idea_hit_rate": 0.4,
            },
            "steady_adapter": {
                "total_signals": 6,
                "insight_hit_rate": 0.2,
                "idea_hit_rate": 0.18,
            },
            "broken_adapter": {
                "total_signals": 0,
                "insight_hit_rate": 0.0,
                "idea_hit_rate": 0.0,
            },
            "low_util_adapter": {
                "total_signals": 4,
                "insight_hit_rate": 0.05,
                "idea_hit_rate": 0.02,
            },
        }

    store.get_adapter_quality_stats = MethodType(get_adapter_quality_stats, store)  # type: ignore[method-assign]
