"""Tests for LLM token efficiency reports."""

from __future__ import annotations

from max.analysis.llm_token_efficiency_report import build_llm_token_efficiency_report
from max.store.db import Store


def test_llm_token_efficiency_ranks_high_token_low_output_runs_first(store: Store) -> None:
    _insert_run(store, "run-expensive", "2026-05-03T00:00:00", 12000, 3000, 1, 0, 0.9, "openai", "gpt-4o")
    _insert_run(store, "run-efficient", "2026-05-02T00:00:00", 900, 100, 40, 12, 0.05, "openai", "gpt-4o-mini")
    _insert_run(store, "run-missing", "2026-05-01T00:00:00", 0, 0, 0, 0, 0.0, "unknown", "gpt-4o-mini")

    report = build_llm_token_efficiency_report(store, limit=10)
    repeated = build_llm_token_efficiency_report(store, limit=10)

    assert report == repeated
    assert report["summary"]["run_count"] == 3
    assert report["summary"]["total_tokens"] == 16000
    assert report["summary"]["high_token_low_output_count"] == 1
    assert [run["id"] for run in report["runs"]] == ["run-expensive", "run-efficient", "run-missing"]
    first = report["runs"][0]
    assert first["input_tokens"] == 12000
    assert first["output_tokens"] == 3000
    assert first["total_tokens"] == 15000
    assert first["token_per_signal"] == 15000.0
    assert first["token_per_unit"] is None
    assert first["efficiency_band"] == "high_token_low_output"
    assert report["efficiency_bands"]["missing_usage"] == ["run-missing"]
    assert any("high-token low-output" in action for action in report["next_actions"])


def test_llm_token_efficiency_rolls_up_models_and_providers(store: Store) -> None:
    _insert_run(store, "run-a", "2026-05-02T00:00:00", 100, 25, 5, 1, 0.01, "openai", "gpt-4o-mini")
    _insert_run(store, "run-b", "2026-05-01T00:00:00", 200, 50, 5, 1, 0.02, "openai", "gpt-4o-mini")

    report = build_llm_token_efficiency_report(store, limit=5)

    assert report["rollups"]["providers"] == [
        {
            "provider": "openai",
            "run_count": 2,
            "input_tokens": 300,
            "output_tokens": 75,
            "total_tokens": 375,
            "estimated_cost_usd": 0.03,
            "output_count": 12,
            "high_token_low_output_count": 0,
            "missing_usage_count": 0,
            "tokens_per_output": 31.25,
        }
    ]
    assert report["rollups"]["models"][0]["model"] == "gpt-4o-mini"


def test_llm_token_efficiency_rejects_invalid_limit(store: Store) -> None:
    try:
        build_llm_token_efficiency_report(store, limit=0)
    except ValueError as exc:
        assert str(exc) == "limit must be at least 1"
    else:
        raise AssertionError("expected ValueError")


def _insert_run(
    store: Store,
    run_id: str,
    started_at: str,
    input_tokens: int,
    output_tokens: int,
    signals: int,
    units: int,
    cost: float,
    provider: str,
    model: str,
) -> None:
    store.insert_pipeline_run(run_id, {"profile": "growth", "domain": "finops", "provider": provider, "model": model})
    store.update_pipeline_run(
        run_id,
        status="completed",
        signals_fetched=signals,
        signals_new=signals,
        insights_generated=max(0, units // 2),
        ideas_generated=units,
        ideas_evaluated=units,
        token_usage={
            "provider": provider,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": cost,
        },
    )
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store._commit()
