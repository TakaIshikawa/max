"""Tests for persisted pipeline replay planning."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from max.analysis.pipeline_replay import (
    PipelineReplayRunNotFound,
    build_pipeline_replay_plan,
)
from max.store.db import Store


def _seed_run(
    store: Store,
    run_id: str = "run-replay-001",
    *,
    config: dict | None = None,
    adapter_metrics: dict | None = None,
    fetch_allocation: dict | None = None,
) -> None:
    store.insert_pipeline_run(
        run_id,
        config
        or {
            "profile": "devtools",
            "signal_limit": 30,
            "min_score": 55.0,
            "weight_profile": "agent_first",
            "ideation_mode": "direct",
            "quality_loop_enabled": True,
            "draft_count": 6,
        },
    )
    store.update_pipeline_run(
        run_id,
        signals_fetched=9,
        signals_new=7,
        insights_generated=3,
        ideas_generated=2,
        ideas_evaluated=2,
        clusters_found=1,
        gaps_detected=4,
        avg_idea_score=71.5,
        fetch_allocation=fetch_allocation or {"hackernews": 10, "github": 20},
        token_usage={"input": 123, "output": 45, "estimated_cost_usd": 0.02},
        adapter_metrics=adapter_metrics
        if adapter_metrics is not None
        else {
            "github": {
                "status": "ok",
                "signal_count": 4,
                "error_message": None,
                "duration_ms": 50,
            },
            "hackernews": {
                "status": "ok",
                "signal_count": 5,
                "error_message": None,
                "duration_ms": 20,
            },
        },
    )


@pytest.fixture
def store():
    s = Store(":memory:")
    try:
        yield s
    finally:
        s.close()


def test_build_pipeline_replay_plan_complete_run(store):
    _seed_run(store)

    plan = build_pipeline_replay_plan(store, "run-replay-001")

    assert plan["run"]["id"] == "run-replay-001"
    assert plan["profile"]["name"] == "devtools"
    assert plan["profile"]["found"] is True
    assert plan["original_metrics"]["signals_fetched"] == 9
    assert plan["original_metrics"]["token_usage"]["input"] == 123
    assert plan["adapter_metrics"]["github"]["signal_count"] == 4
    assert plan["recommended_source_limits"]["github"] == 20
    assert plan["recommended_source_limits"]["hackernews"] == 10
    assert "--dry-run" in plan["dry_run_commands"]["cli"]
    assert "--profile devtools" in plan["dry_run_commands"]["cli"]
    assert plan["dry_run_commands"]["api"]["body"]["profile"] == "devtools"
    assert plan["warnings"] == []


def test_build_pipeline_replay_plan_without_adapter_metrics_degrades(store):
    _seed_run(
        store,
        "run-replay-degraded",
        config={"signal_limit": 12, "min_score": 50.0},
        adapter_metrics={},
        fetch_allocation={},
    )

    plan = build_pipeline_replay_plan(store, "run-replay-degraded")

    assert plan["profile"]["found"] is False
    assert plan["adapter_metrics"] == {}
    assert plan["adapter_inputs"] == []
    assert plan["recommended_source_limits"] == {}
    assert plan["dry_run_commands"]["api"]["body"]["signal_limit"] == 12
    assert any("No profile was recorded" in warning for warning in plan["warnings"])
    assert any("No adapter metrics" in warning for warning in plan["warnings"])


def test_build_pipeline_replay_plan_missing_run_raises(store):
    with pytest.raises(PipelineReplayRunNotFound) as exc:
        build_pipeline_replay_plan(store, "run-missing")

    assert exc.value.run_id == "run-missing"


def test_build_pipeline_replay_plan_warns_for_missing_profile_and_adapter(store):
    _seed_run(
        store,
        "run-replay-warnings",
        config={"profile": "missing-profile", "signal_limit": 8},
        adapter_metrics={
            "ghost_adapter": {
                "status": "error",
                "signal_count": 0,
                "error_message": "not installed",
                "duration_ms": 1,
            }
        },
        fetch_allocation={"ghost_adapter": 8},
    )

    with patch("max.sources.registry.list_adapters", return_value=["github"]):
        plan = build_pipeline_replay_plan(store, "run-replay-warnings")

    assert plan["profile"]["found"] is False
    assert any("missing-profile" in warning for warning in plan["warnings"])
    assert any("ghost_adapter" in warning for warning in plan["warnings"])


def test_build_pipeline_replay_plan_is_deterministic(store):
    _seed_run(store)

    first = build_pipeline_replay_plan(store, "run-replay-001")
    second = build_pipeline_replay_plan(store, "run-replay-001")

    assert first == second
