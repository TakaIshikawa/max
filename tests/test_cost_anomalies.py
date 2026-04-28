from __future__ import annotations

from max.analysis.cost_anomalies import build_cost_anomaly_report
from max.store.db import Store


def _seed_run(
    store: Store,
    run_id: str,
    *,
    started_at: str,
    profile: str = "ai-infra",
    input_tokens: int,
    output_tokens: int,
    cost: float,
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


def test_cost_anomaly_report_flags_run_and_stage_anomalies(store: Store) -> None:
    for index in range(3):
        _seed_run(
            store,
            f"run-base-{index}",
            started_at=f"2026-04-2{index}T00:00:00Z",
            input_tokens=160,
            output_tokens=40,
            cost=0.02,
            by_stage={
                "fetch_signals": {"input": 80, "output": 20},
                "synthesis": {"input": 80, "output": 20},
            },
            cost_by_stage={"fetch_signals": 0.01, "synthesis": 0.01},
        )
    _seed_run(
        store,
        "run-spike",
        started_at="2026-04-24T00:00:00Z",
        input_tokens=800,
        output_tokens=200,
        cost=0.12,
        by_stage={
            "fetch_signals": {"input": 80, "output": 20},
            "synthesis": {"input": 720, "output": 180},
        },
        cost_by_stage={"fetch_signals": 0.01, "synthesis": 0.11},
    )

    report = build_cost_anomaly_report(store, limit=1, z_threshold=2.0)

    assert report["anomaly_count"] == 1
    anomaly = report["anomalies"][0]
    assert anomaly["run_id"] == "run-spike"
    assert anomaly["total_tokens"] == 1000
    assert {item["metric"] for item in anomaly["run_anomalies"]} == {
        "total_tokens",
        "estimated_cost_usd",
    }
    stage_anomaly = next(
        item
        for item in anomaly["stage_anomalies"]
        if item["stage"] == "synthesis" and item["metric"] == "total_tokens"
    )
    assert stage_anomaly["stage"] == "synthesis"
    assert stage_anomaly["baseline"] == 100.0
    assert stage_anomaly["observed"] == 900.0
    assert stage_anomaly["ratio"] == 9.0
    assert "synthesis prompt size" in stage_anomaly["recommendation"]


def test_cost_anomaly_report_returns_empty_for_low_sample_history(store: Store) -> None:
    _seed_run(
        store,
        "run-base",
        started_at="2026-04-20T00:00:00Z",
        input_tokens=100,
        output_tokens=20,
        cost=0.02,
        by_stage={"ideation": {"input": 100, "output": 20}},
        cost_by_stage={"ideation": 0.02},
    )
    _seed_run(
        store,
        "run-spike",
        started_at="2026-04-21T00:00:00Z",
        input_tokens=1000,
        output_tokens=200,
        cost=0.30,
        by_stage={"ideation": {"input": 1000, "output": 200}},
        cost_by_stage={"ideation": 0.30},
    )

    report = build_cost_anomaly_report(store, limit=5)

    assert report["run_count"] == 2
    assert report["anomaly_count"] == 0
    assert report["anomalies"] == []


def test_cost_anomaly_report_baselines_are_profile_scoped(store: Store) -> None:
    for index in range(3):
        _seed_run(
            store,
            f"run-other-{index}",
            started_at=f"2026-04-2{index}T00:00:00Z",
            profile="fintech",
            input_tokens=100,
            output_tokens=20,
            cost=0.01,
        )
    _seed_run(
        store,
        "run-ai-infra",
        started_at="2026-04-24T00:00:00Z",
        profile="ai-infra",
        input_tokens=1000,
        output_tokens=200,
        cost=0.30,
    )

    report = build_cost_anomaly_report(store, limit=1)

    assert report["anomalies"] == []
