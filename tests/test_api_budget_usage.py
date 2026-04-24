"""Tests for the REST LLM budget usage endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max.server.app import create_app
from max.store.db import Store


@pytest.fixture
def budget_api_db(tmp_path):
    db_path = str(tmp_path / "api_budget.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()
    return db_path


@pytest.fixture
def budget_client(budget_api_db):
    from max.server.dependencies import get_store

    app = create_app()

    def override_get_store():
        store = Store(db_path=budget_api_db, wal_mode=True)
        try:
            yield store
        finally:
            store.close()

    app.dependency_overrides[get_store] = override_get_store
    return TestClient(app)


def _seed_run(db_path: str, run_id: str, token_usage: dict[str, object]) -> None:
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_pipeline_run(run_id, {"model": "claude-opus-4-6"})
        store.update_pipeline_run(run_id, token_usage=token_usage)


def test_llm_budget_usage_returns_core_fields_and_honors_limit(
    budget_client, budget_api_db, monkeypatch
):
    _seed_run(
        budget_api_db,
        "run-old",
        {"input": 100, "output": 20, "fetch_input": 80, "fetch_output": 10},
    )
    _seed_run(
        budget_api_db,
        "run-new",
        {"input": 10, "output": 5, "ideate_input": 8, "ideate_output": 4},
    )
    monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 1000)
    monkeypatch.setattr("max.config.MAX_COST_BUDGET", 2.0)

    response = budget_client.get(
        "/api/v1/budget/usage",
        params={"limit": 1, "include_current": "false"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["run_count"] == 1
    assert payload["include_current"] is False
    assert payload["token_budget"] == 1000
    assert payload["cost_budget_usd"] == 2.0
    assert payload["total_tokens"] == 15
    assert payload["remaining_tokens"] == 985
    assert payload["current"] is None
    assert payload["runs"][0]["id"] == "run-new"
    assert payload["stages"][0]["stage"] == "ideate"


def test_llm_budget_usage_rejects_invalid_limit(budget_client):
    response = budget_client.get("/api/v1/budget/usage", params={"limit": 0})

    assert response.status_code == 422
