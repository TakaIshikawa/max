from __future__ import annotations

import pytest

from max.analysis.run_comparison import (
    PipelineRunComparisonNotFound,
    compare_pipeline_runs,
)
from max.store.db import Store


def _seed_run(
    store: Store,
    run_id: str,
    *,
    signals_fetched: int,
    signals_new: int,
    insights_generated: int,
    ideas_generated: int,
    ideas_evaluated: int,
    token_usage: dict,
    adapter_metrics: dict,
) -> None:
    store.insert_pipeline_run(run_id, {"model": "gpt-4o-mini"})
    store.update_pipeline_run(
        run_id,
        signals_fetched=signals_fetched,
        signals_new=signals_new,
        insights_generated=insights_generated,
        ideas_generated=ideas_generated,
        ideas_evaluated=ideas_evaluated,
        clusters_found=2,
        gaps_detected=1,
        avg_idea_score=70.0,
        token_usage=token_usage,
        adapter_metrics=adapter_metrics,
        status="completed",
    )


def test_compare_pipeline_runs_returns_persisted_deltas(store: Store) -> None:
    _seed_run(
        store,
        "run-base",
        signals_fetched=10,
        signals_new=6,
        insights_generated=3,
        ideas_generated=2,
        ideas_evaluated=1,
        token_usage={"input": 100, "output": 25, "estimated_cost_usd": 0.01},
        adapter_metrics={
            "github": {"status": "ok", "signal_count": 6, "duration_ms": 100},
            "hn": {"status": "error", "signal_count": 0, "duration_ms": 20},
        },
    )
    _seed_run(
        store,
        "run-target",
        signals_fetched=18,
        signals_new=11,
        insights_generated=5,
        ideas_generated=4,
        ideas_evaluated=3,
        token_usage={"input": 175, "output": 40, "estimated_cost_usd": 0.02},
        adapter_metrics={
            "github": {"status": "ok", "signal_count": 9, "duration_ms": 130},
            "reddit": {"status": "ok", "signal_count": 4, "duration_ms": 80},
        },
    )
    store.insert_feedback("bu-out-1", "approved", pipeline_run_id="run-target")
    store.insert_feedback("bu-out-2", "published", pipeline_run_id="run-target")

    result = compare_pipeline_runs(
        store,
        base_run_id="run-base",
        target_run_id="run-target",
    )

    assert result["fetched_signals"]["signals_fetched"]["delta"] == 8
    assert result["insights"]["insights_generated"]["delta"] == 2
    assert result["generated_ideas"]["ideas_generated"]["delta"] == 2
    assert result["approved_published_outputs"]["approved_or_published"]["target"] == 2
    assert result["budget_usage"]["total_tokens"]["delta"] == 90

    adapters = {row["adapter"]: row for row in result["adapter_metrics"]}
    assert adapters["github"]["metrics"]["signal_count"]["delta"] == 3
    assert adapters["hn"]["target_status"] is None
    assert adapters["reddit"]["base_status"] is None


def test_compare_pipeline_runs_reports_missing_ids(store: Store) -> None:
    _seed_run(
        store,
        "run-base",
        signals_fetched=1,
        signals_new=1,
        insights_generated=0,
        ideas_generated=0,
        ideas_evaluated=0,
        token_usage={},
        adapter_metrics={},
    )

    with pytest.raises(PipelineRunComparisonNotFound) as exc:
        compare_pipeline_runs(
            store,
            base_run_id="run-base",
            target_run_id="run-missing",
        )

    assert exc.value.missing_run_ids == ["run-missing"]
