from __future__ import annotations

import json

from max.api.budget_usage import SCHEMA_VERSION, budget_usage_to_json
from max.analysis.budget_usage import build_llm_budget_usage
from max.llm.client import TokenTracker
from max.store.db import Store


def test_budget_usage_to_json_returns_valid_json(tmp_path, monkeypatch) -> None:
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
            },
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)

        parsed = json.loads(json_output)
        assert isinstance(parsed, dict)
        assert parsed["schema_version"] == SCHEMA_VERSION
        assert parsed["kind"] == "max.api.budget_usage"
    finally:
        store.close()


def test_budget_usage_to_json_includes_summary(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "summary" in parsed
        summary = parsed["summary"]
        assert summary["run_count"] == 1
        assert summary["total_tokens"] == 1100
        assert summary["total_input"] == 1000
        assert summary["total_output"] == 100
        assert summary["total_cost_usd"] > 0
    finally:
        store.close()


def test_budget_usage_to_json_includes_budget_limits(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "budget_limits" in parsed
        limits = parsed["budget_limits"]
        assert limits["token_budget"] == 5000
        assert limits["cost_budget_usd"] == 1.0
        assert limits["remaining_tokens"] == 3900
        assert limits["remaining_cost_usd"] is not None
    finally:
        store.close()


def test_budget_usage_to_json_includes_stage_aggregations(tmp_path, monkeypatch) -> None:
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
                "evaluate_input": 400,
                "evaluate_output": 40,
            },
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "stage_aggregations" in parsed
        stages = parsed["stage_aggregations"]
        assert len(stages) >= 2

        stage_map = {s["stage"]: s for s in stages}
        assert "synthesis" in stage_map
        assert "evaluate" in stage_map

        assert stage_map["synthesis"]["input_tokens"] == 600
        assert stage_map["synthesis"]["output_tokens"] == 60
        assert stage_map["synthesis"]["total_tokens"] == 660
        assert stage_map["synthesis"]["estimated_cost_usd"] > 0
    finally:
        store.close()


def test_budget_usage_to_json_includes_current_session(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )

        tracker = TokenTracker(model="claude-opus-4-6")
        tracker.record("evaluate", 300, 30)

        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, tracker=tracker)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "current_session" in parsed
        current = parsed["current_session"]
        assert current is not None
        assert current["input_tokens"] == 300
        assert current["output_tokens"] == 30
        assert current["total_tokens"] == 330
        assert current["estimated_cost_usd"] > 0
        assert len(current["stages"]) == 1
        assert current["stages"][0]["stage"] == "evaluate"
    finally:
        store.close()


def test_budget_usage_to_json_current_session_null_when_not_included(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "current_session" in parsed
        assert parsed["current_session"] is None
    finally:
        store.close()


def test_budget_usage_to_json_includes_spend_by_category(tmp_path, monkeypatch) -> None:
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
                "evaluate_input": 400,
                "evaluate_output": 40,
            },
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "spend_by_category" in parsed
        spend = parsed["spend_by_category"]
        assert "by_stage" in spend
        assert "synthesis" in spend["by_stage"]
        assert "evaluate" in spend["by_stage"]
        assert spend["total_cost_usd"] > 0
        assert spend["stage_count"] == 2
    finally:
        store.close()


def test_budget_usage_to_json_includes_variance_metrics(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 2000, "total_output": 200},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "variance_metrics" in parsed
        metrics = parsed["variance_metrics"]
        assert "token_utilization_percent" in metrics
        assert "cost_utilization_percent" in metrics
        assert metrics["token_utilization_percent"] == 44.0  # 2200/5000 * 100
        assert metrics["over_token_budget"] is False
        assert metrics["over_cost_budget"] is False
    finally:
        store.close()


def test_budget_usage_to_json_includes_forecast_projections(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        store.insert_pipeline_run("run-002", {})
        store.update_pipeline_run(
            "run-002",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "forecast_projections" in parsed
        forecast = parsed["forecast_projections"]
        assert forecast["projected_tokens_per_run"] == 1100  # (1100+1100)/2
        assert forecast["projected_cost_per_run_usd"] > 0
        assert forecast["runs_until_token_budget_exhausted"] is not None
        assert forecast["runs_until_cost_budget_exhausted"] is not None
    finally:
        store.close()


def test_budget_usage_to_json_includes_runs_breakdown(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        store.insert_pipeline_run("run-002", {"model": "claude-opus-4-6"})
        store.update_pipeline_run(
            "run-002",
            token_usage={"total_input": 500, "total_output": 50},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)
        parsed = json.loads(json_output)

        assert "runs" in parsed
        runs = parsed["runs"]
        assert len(runs) == 2
        assert runs[0]["id"] in ["run-001", "run-002"]
        assert "started_at" in runs[0]
        assert "status" in runs[0]
        assert runs[0]["total_tokens"] > 0
    finally:
        store.close()


def test_budget_usage_to_json_deterministic(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        first = budget_usage_to_json(usage)
        second = budget_usage_to_json(usage)

        assert first == second
    finally:
        store.close()


def test_budget_usage_to_json_sorted_keys(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "budget.db"
    store = Store(db_path=db_path, wal_mode=True)
    try:
        store.insert_pipeline_run("run-001", {})
        store.update_pipeline_run(
            "run-001",
            token_usage={"total_input": 1000, "total_output": 100},
        )
        monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 5000)
        monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

        usage = build_llm_budget_usage(store, limit=20, include_current=False)
        json_output = budget_usage_to_json(usage)

        parsed = json.loads(json_output)
        resorted = json.dumps(parsed, indent=2, sort_keys=True)
        assert json_output == resorted
    finally:
        store.close()
