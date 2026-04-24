from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


@pytest.fixture
def pipeline_export_db(tmp_path: Path) -> str:
    path = str(tmp_path / "pipeline_export.db")
    store = Store(db_path=path, wal_mode=True)
    try:
        store.insert_pipeline_run(
            "run-api-export",
            {"profile": "ai-infra", "domain": "ai infrastructure", "model": "gpt-4o-mini"},
        )
        store.update_pipeline_run(
            "run-api-export",
            signals_fetched=5,
            signals_new=4,
            insights_generated=2,
            ideas_generated=1,
            ideas_evaluated=1,
            token_usage={"input": 400, "output": 100, "estimated_cost_usd": 0.004},
            adapter_metrics={
                "github": {
                    "status": "ok",
                    "signal_count": 5,
                    "duration_ms": 80,
                    "error_message": None,
                }
            },
            status="completed",
        )
        store.insert_pipeline_run_domain(
            "run-api-export",
            "ai infrastructure",
            {
                "signals_fetched": 5,
                "insights_generated": 2,
                "ideas_generated": 1,
                "ideas_evaluated": 1,
                "avg_score": 71.0,
            },
        )
    finally:
        store.close()
    return path


@pytest.fixture
def pipeline_export_client(pipeline_export_db: str) -> TestClient:
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=pipeline_export_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def test_export_recent_pipeline_runs_json_route(pipeline_export_client: TestClient) -> None:
    response = pipeline_export_client.get("/api/v1/pipeline/runs/export?format=json&limit=5")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert data["run_count"] == 1
    assert data["runs"][0]["id"] == "run-api-export"
    assert data["runs"][0]["budget"]["total_tokens"] == 500
    assert data["runs"][0]["adapter_stats"][0]["adapter"] == "github"


def test_export_recent_pipeline_runs_markdown_route(pipeline_export_client: TestClient) -> None:
    response = pipeline_export_client.get("/api/v1/pipeline/runs/export?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "## Run run-api-export" in response.text
    assert "### Adapter Stats" in response.text


def test_export_single_pipeline_run_json_route(pipeline_export_client: TestClient) -> None:
    response = pipeline_export_client.get("/api/v1/pipeline/runs/run-api-export/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert data["id"] == "run-api-export"
    assert data["profile"] == "ai-infra"
    assert data["domain"] == "ai infrastructure"


def test_export_single_pipeline_run_markdown_route(pipeline_export_client: TestClient) -> None:
    response = pipeline_export_client.get("/api/v1/pipeline/runs/run-api-export/export?format=markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# Pipeline Run run-api-export Export" in response.text
    assert "Total tokens: 500" in response.text


def test_export_single_pipeline_run_unknown_id_returns_404(
    pipeline_export_client: TestClient,
) -> None:
    response = pipeline_export_client.get("/api/v1/pipeline/runs/run-missing/export")

    assert response.status_code == 404
    assert response.json()["detail"]["run_id"] == "run-missing"
