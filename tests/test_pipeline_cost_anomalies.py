from __future__ import annotations

from max.analysis.pipeline_cost_anomalies import build_pipeline_cost_anomaly_report
from max.store.db import Store


def _seed_run(
    store: Store,
    run_id: str,
    *,
    started_at: str,
    profile: str = "ai-infra",
    cost: float,
    input_tokens: int = 100,
    output_tokens: int = 50,
    by_stage: dict[str, dict[str, int]] | None = None,
    cost_by_stage: dict[str, float] | None = None,
) -> None:
    store.insert_pipeline_run(run_id, {"profile": profile, "model": "claude-haiku-4-5-20251001"})
    store.update_pipeline_run(
        run_id,
        token_usage={
            "input": input_tokens,
            "output": output_tokens,
            "estimated_cost_usd": cost,
            "by_stage": by_stage or {},
            "cost_by_stage": cost_by_stage or {},
        },
        status="completed",
    )
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store.conn.commit()


def test_cost_anomaly_report_empty_when_baseline_is_insufficient(store: Store) -> None:
    _seed_run(store, "run-baseline-1", started_at="2026-04-20T00:00:00Z", cost=0.02)
    _seed_run(store, "run-spike", started_at="2026-04-21T00:00:00Z", cost=0.50)

    report = build_pipeline_cost_anomaly_report(
        store,
        limit=5,
        baseline_window=3,
        min_cost_usd=0.05,
        multiplier_threshold=2.0,
    )

    assert report["anomaly_count"] == 0
    assert report["anomalies"] == []


def test_cost_anomaly_report_flags_cost_and_multiplier_reasons(store: Store) -> None:
    _seed_run(store, "run-base-1", started_at="2026-04-20T00:00:00Z", cost=0.02)
    _seed_run(store, "run-base-2", started_at="2026-04-21T00:00:00Z", cost=0.03)
    _seed_run(store, "run-base-3", started_at="2026-04-22T00:00:00Z", cost=0.01)
    _seed_run(
        store,
        "run-spike",
        started_at="2026-04-23T00:00:00Z",
        cost=0.12,
        input_tokens=2400,
        output_tokens=600,
        by_stage={
            "synthesis": {"input": 400, "output": 100},
            "ideation": {"input": 2000, "output": 500},
        },
        cost_by_stage={"synthesis": 0.02, "ideation": 0.10},
    )

    report = build_pipeline_cost_anomaly_report(
        store,
        limit=1,
        baseline_window=3,
        min_cost_usd=0.05,
        multiplier_threshold=2.0,
    )

    assert report["anomaly_count"] == 1
    anomaly = report["anomalies"][0]
    assert anomaly["run_id"] == "run-spike"
    assert anomaly["profile"] == "ai-infra"
    assert anomaly["total_tokens"] == 3000
    assert anomaly["estimated_cost_usd"] == 0.12
    assert anomaly["baseline_cost_usd"] == 0.02
    assert anomaly["multiplier"] == 6.0
    assert anomaly["anomaly_reasons"] == [
        "estimated cost $0.1200 is at or above threshold $0.0500",
        "estimated cost is 6.00x the rolling baseline $0.0200",
    ]
    assert anomaly["top_stage_metrics"][0]["stage"] == "ideation"
    assert anomaly["top_stage_metrics"][0]["total_tokens"] == 2500


def test_cost_anomaly_baseline_is_profile_scoped(store: Store) -> None:
    _seed_run(store, "run-other-1", started_at="2026-04-20T00:00:00Z", profile="fintech", cost=0.01)
    _seed_run(store, "run-other-2", started_at="2026-04-21T00:00:00Z", profile="fintech", cost=0.01)
    _seed_run(store, "run-spike", started_at="2026-04-22T00:00:00Z", profile="ai-infra", cost=0.50)

    report = build_pipeline_cost_anomaly_report(
        store,
        limit=3,
        baseline_window=2,
        min_cost_usd=0.05,
        multiplier_threshold=2.0,
    )

    assert report["anomalies"] == []
