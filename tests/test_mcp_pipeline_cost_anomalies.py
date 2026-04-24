from __future__ import annotations

import json
from pathlib import Path

import pytest

from max.server import mcp_tools
from max.server.mcp_tools import (
    max_pipeline_cost_anomalies,
    pipeline_cost_anomalies_detail,
    set_store_factory,
)
from max.store.db import Store


def _seed_run(
    store: Store,
    run_id: str,
    *,
    started_at: str,
    cost: float,
    input_tokens: int = 100,
    output_tokens: int = 50,
    profile: str = "ai-infra",
) -> None:
    store.insert_pipeline_run(run_id, {"profile": profile, "model": "claude-haiku-4-5-20251001"})
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
def mcp_cost_anomaly_db(tmp_path: Path) -> str:
    db_path = str(tmp_path / "mcp_pipeline_cost_anomalies.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def test_max_pipeline_cost_anomalies_returns_rest_shape_with_warning_fields(
    mcp_cost_anomaly_db: str,
) -> None:
    with Store(db_path=mcp_cost_anomaly_db, wal_mode=True) as store:
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

    report = max_pipeline_cost_anomalies(
        limit=1,
        baseline_window=2,
        multiplier_threshold=2.0,
        min_cost_usd=0.05,
    )

    assert report["limit"] == 1
    assert report["baseline_window"] == 2
    assert report["min_cost_usd"] == 0.05
    assert report["multiplier_threshold"] == 2.0
    assert report["anomaly_count"] == 1
    assert report["has_cost_anomaly_warnings"] is True
    anomaly = report["anomalies"][0]
    assert anomaly["run_id"] == "run-spike"
    assert anomaly["profile"] == "ai-infra"
    assert anomaly["total_tokens"] == 1200
    assert anomaly["estimated_cost_usd"] == 0.09
    assert anomaly["baseline_cost_usd"] == 0.02
    assert anomaly["multiplier"] == 4.5
    assert anomaly["anomaly_reasons"]
    assert anomaly["cost_anomaly_warning"] is True
    assert anomaly["warning_reasons"] == anomaly["anomaly_reasons"]
    assert anomaly["warning"]
    assert anomaly["top_stage_metrics"][0]["stage"] == "ideation"
    json.dumps(report)


def test_max_pipeline_cost_anomalies_parameters_override_defaults(
    mcp_cost_anomaly_db: str,
) -> None:
    with Store(db_path=mcp_cost_anomaly_db, wal_mode=True) as store:
        _seed_run(store, "run-base-1", started_at="2026-04-20T00:00:00Z", cost=0.03)
        _seed_run(store, "run-base-2", started_at="2026-04-21T00:00:00Z", cost=0.03)
        _seed_run(store, "run-small-rise", started_at="2026-04-22T00:00:00Z", cost=0.04)

    default_threshold_report = max_pipeline_cost_anomalies(
        limit=1,
        baseline_window=2,
    )
    override_report = max_pipeline_cost_anomalies(
        limit=1,
        baseline_window=2,
        multiplier_threshold=1.2,
        min_cost_usd=0.03,
    )

    assert default_threshold_report["anomaly_count"] == 0
    assert default_threshold_report["has_cost_anomaly_warnings"] is False
    assert override_report["anomaly_count"] == 1
    assert override_report["multiplier_threshold"] == 1.2
    assert override_report["min_cost_usd"] == 0.03
    assert override_report["anomalies"][0]["run_id"] == "run-small-rise"


def test_pipeline_cost_anomalies_resource_returns_default_json(
    mcp_cost_anomaly_db: str,
) -> None:
    with Store(db_path=mcp_cost_anomaly_db, wal_mode=True) as store:
        for index in range(5):
            _seed_run(
                store,
                f"run-base-{index}",
                started_at=f"2026-04-2{index}T00:00:00Z",
                cost=0.02,
            )
        _seed_run(
            store,
            "run-resource-spike",
            started_at="2026-04-25T00:00:00Z",
            cost=0.09,
        )

    payload = json.loads(pipeline_cost_anomalies_detail())

    assert payload["limit"] == 20
    assert payload["baseline_window"] == 5
    assert payload["anomaly_count"] == 1
    assert payload["anomalies"][0]["run_id"] == "run-resource-spike"
    assert payload["anomalies"][0]["cost_anomaly_warning"] is True


def test_create_mcp_server_registers_pipeline_cost_anomaly_tool_and_resource(
    monkeypatch: pytest.MonkeyPatch,
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

    assert "max_pipeline_cost_anomalies" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["pipeline://cost-anomalies"]
        == "pipeline_cost_anomalies_detail"
    )
