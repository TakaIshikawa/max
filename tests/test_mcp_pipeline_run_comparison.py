"""Tests for pipeline run comparison exposed through MCP."""

from __future__ import annotations

import json

import pytest

from max.server import mcp_tools
from max.server.mcp_tools import (
    compare_pipeline_runs,
    pipeline_run_comparison_detail,
    set_store_factory,
)
from max.store.db import Store


def _seed_pipeline_run(
    store: Store,
    run_id: str,
    *,
    signals_fetched: int,
    signals_new: int,
    insights_generated: int,
    ideas_generated: int,
    ideas_evaluated: int,
    avg_idea_score: float,
    token_usage: dict[str, object],
    adapter_metrics: dict[str, dict[str, object]],
) -> None:
    store.insert_pipeline_run(run_id, {"model": "gpt-4o-mini", "profile": "devtools"})
    store.update_pipeline_run(
        run_id,
        signals_fetched=signals_fetched,
        signals_new=signals_new,
        insights_generated=insights_generated,
        ideas_generated=ideas_generated,
        ideas_evaluated=ideas_evaluated,
        clusters_found=2,
        gaps_detected=1,
        avg_idea_score=avg_idea_score,
        token_usage=token_usage,
        adapter_metrics=adapter_metrics,
        status="completed",
    )


def _seed_comparison(store: Store) -> None:
    _seed_pipeline_run(
        store,
        "run-baseline",
        signals_fetched=10,
        signals_new=6,
        insights_generated=3,
        ideas_generated=2,
        ideas_evaluated=1,
        avg_idea_score=64.0,
        token_usage={"input": 100, "output": 25, "estimated_cost_usd": 0.01},
        adapter_metrics={
            "github": {"status": "ok", "signal_count": 6, "duration_ms": 100},
            "hackernews": {
                "status": "error",
                "signal_count": 0,
                "duration_ms": 20,
                "error_message": "rate limited",
            },
        },
    )
    _seed_pipeline_run(
        store,
        "run-candidate",
        signals_fetched=18,
        signals_new=11,
        insights_generated=5,
        ideas_generated=4,
        ideas_evaluated=3,
        avg_idea_score=70.5,
        token_usage={"input": 175, "output": 40, "estimated_cost_usd": 0.02},
        adapter_metrics={
            "github": {"status": "ok", "signal_count": 9, "duration_ms": 130},
            "reddit": {"status": "ok", "signal_count": 4, "duration_ms": 80},
        },
    )
    store.insert_feedback("bu-out-1", "approved", pipeline_run_id="run-candidate")
    store.insert_feedback("bu-out-2", "published", pipeline_run_id="run-candidate")


@pytest.fixture
def mcp_comparison_db(tmp_path):
    db_path = str(tmp_path / "mcp_pipeline_run_comparison.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def test_compare_pipeline_runs_returns_seeded_metric_deltas(mcp_comparison_db) -> None:
    with Store(db_path=mcp_comparison_db, wal_mode=True) as store:
        _seed_comparison(store)

    result = compare_pipeline_runs("run-baseline", "run-candidate")

    assert result["base_run"]["id"] == "run-baseline"
    assert result["target_run"]["id"] == "run-candidate"
    assert result["fetched_signals"]["signals_fetched"] == {
        "base": 10,
        "target": 18,
        "delta": 8,
    }
    assert result["generated_ideas"]["avg_idea_score"]["delta"] == 6.5
    assert result["approved_published_outputs"]["approved_or_published"]["target"] == 2
    assert result["budget_usage"]["total_tokens"]["delta"] == 90

    adapters = {row["adapter"]: row for row in result["adapter_metrics"]}
    assert adapters["github"]["metrics"]["signal_count"]["delta"] == 3
    assert adapters["hackernews"]["target_status"] is None
    assert adapters["hackernews"]["base_error_message"] == "rate limited"
    assert adapters["reddit"]["base_status"] is None


def test_compare_pipeline_runs_can_omit_adapter_metrics(mcp_comparison_db) -> None:
    with Store(db_path=mcp_comparison_db, wal_mode=True) as store:
        _seed_comparison(store)

    result = compare_pipeline_runs(
        "run-baseline",
        "run-candidate",
        include_adapter_metrics=False,
    )

    assert result["fetched_signals"]["signals_new"]["delta"] == 5
    assert "adapter_metrics" not in result


def test_compare_pipeline_runs_missing_run_returns_mcp_error(mcp_comparison_db) -> None:
    with Store(db_path=mcp_comparison_db, wal_mode=True) as store:
        _seed_pipeline_run(
            store,
            "run-baseline",
            signals_fetched=1,
            signals_new=1,
            insights_generated=0,
            ideas_generated=0,
            ideas_evaluated=0,
            avg_idea_score=0.0,
            token_usage={},
            adapter_metrics={},
        )

    result = compare_pipeline_runs("run-baseline", "run-missing")

    assert result == {
        "error": "Pipeline run ID not found",
        "code": 404,
        "details": {
            "missing_run_ids": ["run-missing"],
            "resource_type": "pipeline_run",
            "resource_id": "run-missing",
        },
    }


def test_pipeline_run_comparison_resource_returns_default_json(mcp_comparison_db) -> None:
    with Store(db_path=mcp_comparison_db, wal_mode=True) as store:
        _seed_comparison(store)

    payload = json.loads(pipeline_run_comparison_detail("run-baseline", "run-candidate"))

    assert payload["target_run"]["id"] == "run-candidate"
    assert payload["insights"]["insights_generated"]["delta"] == 2
    assert payload["adapter_metrics"][0]["adapter"] == "github"


def test_create_mcp_server_registers_pipeline_run_comparison_tool_and_resource(
    monkeypatch,
) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name):
            self.name = name
            self.tools = []
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn):
            self.tools.append(fn.__name__)
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    mcp_tools.create_mcp_server()

    assert "compare_pipeline_runs" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources[
            "pipeline-run-comparisons://{baseline_run_id}/{candidate_run_id}"
        ]
        == "pipeline_run_comparison_detail"
    )
