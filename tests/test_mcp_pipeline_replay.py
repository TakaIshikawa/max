"""Tests for pipeline replay plans exposed through MCP."""

from __future__ import annotations

import pytest

from max.server.mcp_tools import get_pipeline_replay_plan, set_store_factory
from max.store.db import Store


def _seed_pipeline_run(store: Store, run_id: str = "run-mcp-replay") -> None:
    store.insert_pipeline_run(
        run_id,
        {
            "profile": "devtools",
            "signal_limit": 24,
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
        fetch_allocation={"github": 14, "hackernews": 10},
        token_usage={"input": 123, "output": 45, "estimated_cost_usd": 0.02},
        adapter_metrics={
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
def mcp_pipeline_db(tmp_path):
    db_path = str(tmp_path / "mcp_pipeline_replay.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def test_get_pipeline_replay_plan_returns_rest_core_fields(mcp_pipeline_db):
    with Store(db_path=mcp_pipeline_db, wal_mode=True) as store:
        _seed_pipeline_run(store)

    result = get_pipeline_replay_plan("run-mcp-replay")

    assert result["run"]["id"] == "run-mcp-replay"
    assert result["profile"]["name"] == "devtools"
    assert result["original_config"]["signal_limit"] == 24
    assert result["original_metrics"]["signals_fetched"] == 9
    assert result["original_metrics"]["token_usage"]["input"] == 123
    adapter_inputs = {row["adapter"]: row for row in result["adapter_inputs"]}
    assert adapter_inputs["github"]["observed_signal_count"] == 4
    assert result["dry_run_commands"]["api"]["body"]["profile"] == "devtools"
    assert "--dry-run" in result["dry_run_commands"]["cli"]
    assert "warnings" in result


def test_get_pipeline_replay_plan_can_omit_commands(mcp_pipeline_db):
    with Store(db_path=mcp_pipeline_db, wal_mode=True) as store:
        _seed_pipeline_run(store)

    result = get_pipeline_replay_plan("run-mcp-replay", include_commands=False)

    assert result["run"]["id"] == "run-mcp-replay"
    assert "dry_run_commands" not in result


def test_get_pipeline_replay_plan_missing_run_returns_mcp_error(mcp_pipeline_db):
    result = get_pipeline_replay_plan("run-missing")

    assert result == {
        "error": "Pipeline run ID not found",
        "code": 404,
        "details": {
            "resource_type": "pipeline_run",
            "resource_id": "run-missing",
        },
    }
