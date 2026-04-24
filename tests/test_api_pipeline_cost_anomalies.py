from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


def _seed_run(
    store: Store,
    run_id: str,
    *,
    started_at: str,
    cost: float,
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> None:
    store.insert_pipeline_run(run_id, {"profile": "ai-infra", "model": "claude-haiku-4-5-20251001"})
    store.update_pipeline_run(
        run_id,
        token_usage={
            "input": input_tokens,
            "output": output_tokens,
            "estimated_cost_usd": cost,
            "by_stage": {"ideation": {"input": input_tokens, "output": output_tokens}},
            "cost_by_stage": {"ideation": cost},
        },
        status="completed",
    )
    store.conn.execute(
        "UPDATE pipeline_runs SET started_at = ?, completed_at = ? WHERE id = ?",
        (started_at, started_at, run_id),
    )
    store.conn.commit()


@pytest.fixture
def pipeline_cost_anomaly_db(tmp_path: Path) -> str:
    path = str(tmp_path / "pipeline_cost_anomalies.db")
    store = Store(db_path=path, wal_mode=True)
    try:
        _seed_run(store, "run-base-1", started_at="2026-04-20T00:00:00Z", cost=0.02)
        _seed_run(store, "run-base-2", started_at="2026-04-21T00:00:00Z", cost=0.02)
        _seed_run(
            store,
            "run-spike",
            started_at="2026-04-22T00:00:00Z",
            cost=0.09,
            input_tokens=900,
            output_tokens=300,
        )
    finally:
        store.close()
    return path


@pytest.fixture
def pipeline_cost_anomaly_client(pipeline_cost_anomaly_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=pipeline_cost_anomaly_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_pipeline_cost_anomalies_route_returns_schema_backed_report(
    pipeline_cost_anomaly_client: TestClient,
) -> None:
    response = pipeline_cost_anomaly_client.get(
        "/api/v1/pipeline/cost-anomalies",
        params={
            "limit": 1,
            "baseline_window": 2,
            "min_cost_usd": 0.05,
            "multiplier_threshold": 2.0,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 1
    assert data["baseline_window"] == 2
    assert data["anomaly_count"] == 1
    anomaly = data["anomalies"][0]
    assert anomaly["run_id"] == "run-spike"
    assert anomaly["profile"] == "ai-infra"
    assert anomaly["total_tokens"] == 1200
    assert anomaly["baseline_cost_usd"] == 0.02
    assert anomaly["multiplier"] == 4.5
    assert anomaly["anomaly_reasons"]
    assert anomaly["top_stage_metrics"][0]["stage"] == "ideation"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"baseline_window": 0},
        {"min_cost_usd": -0.01},
        {"multiplier_threshold": 0},
    ],
)
def test_pipeline_cost_anomalies_route_validates_query_parameters(
    pipeline_cost_anomaly_client: TestClient,
    params: dict[str, float],
) -> None:
    response = pipeline_cost_anomaly_client.get("/api/v1/pipeline/cost-anomalies", params=params)

    assert response.status_code == 422
