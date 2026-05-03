"""Tests for LLM budget usage aggregation."""

from __future__ import annotations

import pytest

from max.analysis.budget_usage import build_llm_budget_usage
from max.llm.client import TokenTracker
from max.store.db import Store


def test_budget_usage_aggregates_runs_stages_and_current(tmp_path, monkeypatch):
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-001",
            token_usage={
                "total_input": 1000,
                "total_output": 100,
                "synthesis_input": 600,
                "synthesis_output": 60,
                "cost_by_stage": {"synthesis": 0.0135},
            },
        )
        store.insert_pipeline_run("run-002", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-002",
            token_usage={
                "input": 2000,
                "output": 200,
                "ideate_input": 1200,
                "ideate_output": 120,
            },
        )

        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("evaluate", 300, 30)
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, tracker=tracker)
    finally:
        store.close()

    assert usage["run_count"] == 2
    assert usage["total_input"] == 3300
    assert usage["total_output"] == 330
    assert usage["total_tokens"] == 3630
    assert usage["remaining_tokens"] == 1370
    assert usage["remaining_cost_usd"] == pytest.approx(0.92575)
    assert {stage["stage"] for stage in usage["stages"]} == {
        "evaluate",
        "ideate",
        "synthesis",
    }


def test_budget_usage_can_omit_current(tmp_path):
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"input": 10, "output": 5},
        )
        usage = build_llm_budget_usage(store, include_current=False)
    finally:
        store.close()

    assert usage["include_current"] is False
    assert usage["current"] is None
    assert usage["total_tokens"] == 15


def test_budget_usage_includes_tracker_stages_in_totals(tmp_path):
    """Verify current tracker stages merge into total stage aggregation."""
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-001",
            token_usage={
                "input": 500,
                "output": 50,
                "evaluate_input": 500,
                "evaluate_output": 50,
            },
        )

        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("evaluate", 200, 20)
        tracker.record("synthesize", 300, 30)

        usage = build_llm_budget_usage(store, limit=20, tracker=tracker)
    finally:
        store.close()

    assert usage["include_current"] is True
    assert usage["current"] is not None
    assert len(usage["current"]["stages"]) == 2

    stage_map = {s["stage"]: s for s in usage["stages"]}
    assert "evaluate" in stage_map
    assert "synthesize" in stage_map

    assert stage_map["evaluate"]["input_tokens"] == 700
    assert stage_map["evaluate"]["output_tokens"] == 70
    assert stage_map["synthesize"]["input_tokens"] == 300
    assert stage_map["synthesize"]["output_tokens"] == 30
