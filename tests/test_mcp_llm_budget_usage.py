"""Tests for MCP LLM budget usage reporting."""

from __future__ import annotations

import json

import pytest

from max.llm.client import TokenTracker
from max.server.mcp_tools import (
    create_mcp_server,
    llm_budget_usage_detail,
    max_llm_budget_usage,
    set_store_factory,
)
from max.store.db import Store


@pytest.fixture
def mcp_budget_db(tmp_path):
    db_path = str(tmp_path / "mcp_budget.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _seed_run(db_path: str, run_id: str, token_usage: dict[str, object]) -> None:
    with Store(db_path=db_path, wal_mode=True) as store:
        store.insert_pipeline_run(run_id, {"model": "claude-opus-4-6"})
        store.update_pipeline_run(run_id, token_usage=token_usage)


def test_max_llm_budget_usage_returns_budget_report_with_limit_and_indicators(
    mcp_budget_db, monkeypatch
):
    _seed_run(
        mcp_budget_db,
        "run-001",
        {
            "input": 60,
            "output": 20,
            "fetch_input": 40,
            "fetch_output": 10,
            "estimated_cost_usd": 0.30,
        },
    )
    _seed_run(
        mcp_budget_db,
        "run-002",
        {
            "input": 30,
            "output": 10,
            "ideate_input": 25,
            "ideate_output": 5,
            "estimated_cost_usd": 0.10,
        },
    )
    tracker = TokenTracker(model="claude-opus-4-6")
    tracker.record("evaluate", 10, 5)
    monkeypatch.setattr("max.llm.client.token_tracker", tracker)
    monkeypatch.setattr("max.config.MAX_TOKEN_BUDGET", 60)
    monkeypatch.setattr("max.config.MAX_COST_BUDGET", 1.0)

    report = max_llm_budget_usage(run_limit=1)

    assert report["limit"] == 1
    assert report["run_count"] == 1
    assert len(report["runs"]) == 1
    assert report["total_tokens"] == 55
    assert report["remaining_tokens"] == 5
    assert report["budget_warning"] is True
    assert report["budget_exceeded"] is False
    assert report["token_budget_warning"] is True
    assert report["token_budget_exceeded"] is False
    assert {stage["stage"] for stage in report["stages"]} == {"evaluate", "ideate"}
    assert report["current"]["stages"][0]["stage"] == "evaluate"


def test_max_llm_budget_usage_invalid_run_limit_returns_validation_error(mcp_budget_db):
    result = max_llm_budget_usage(run_limit=0)

    assert result["error"] == "run_limit must be between 1 and 500"
    assert result["code"] == 400
    assert result["details"]["field"] == "run_limit"
    assert result["details"]["expected"] == "integer between 1 and 500"
    assert result["details"]["actual"] == "0"


def test_llm_budget_usage_resource_returns_default_report(mcp_budget_db, monkeypatch):
    _seed_run(
        mcp_budget_db,
        "run-resource",
        {"input": 5, "output": 2, "estimated_cost_usd": 0.01},
    )
    tracker = TokenTracker(model="claude-opus-4-6")
    monkeypatch.setattr("max.llm.client.token_tracker", tracker)

    payload = json.loads(llm_budget_usage_detail())

    assert payload["limit"] == 20
    assert payload["run_count"] == 1
    assert payload["runs"][0]["id"] == "run-resource"
    assert "budget_warning" in payload
    assert "budget_exceeded" in payload


def test_create_mcp_server_registers_llm_budget_tool_and_resource(monkeypatch):
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

    monkeypatch.setattr("max.server.mcp_tools.FastMCP", FakeMCP)

    create_mcp_server()

    assert "max_llm_budget_usage" in FakeMCP.latest.tools
    assert FakeMCP.latest.resources["budget://llm-usage"] == "llm_budget_usage_detail"
