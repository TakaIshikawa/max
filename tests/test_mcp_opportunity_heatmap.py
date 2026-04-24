"""Tests for MCP opportunity heatmap exposure."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from max.server.mcp_tools import (
    create_mcp_server,
    max_opportunity_heatmap,
    opportunity_heatmap_detail,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_db(tmp_path):
    """Create temp DB and configure mcp_tools to use it."""
    db_path = str(tmp_path / "test_mcp_opportunity_heatmap.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


def _signal(signal_id: str, *, fetched_at: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title=f"Signal {signal_id}",
        content="Evidence",
        url=f"https://example.com/{signal_id}",
        fetched_at=datetime.fromisoformat(fetched_at).replace(tzinfo=timezone.utc),
        credibility=0.8,
    )


def _unit(
    unit_id: str,
    *,
    domain: str,
    category: str,
    evidence_signals: list[str],
    status: str = "evaluated",
) -> BuildableUnit:
    return BuildableUnit(
        id=unit_id,
        title=f"Idea {unit_id}",
        one_liner="Test idea",
        category=category,
        problem="Problem",
        solution="Solution",
        value_proposition="Value",
        domain=domain,
        evidence_signals=evidence_signals,
        status=status,
    )


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="test")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=dim,
        timing_fit=dim,
        compounding_value=dim,
        overall_score=score,
        recommendation="yes",
    )


def test_max_opportunity_heatmap_returns_ranked_bucket_dicts(mcp_db) -> None:
    with Store(db_path=mcp_db, wal_mode=True) as store:
        store.insert_signal(_signal("sig-1", fetched_at="2026-04-20T00:00:00"))
        store.insert_buildable_unit(
            _unit(
                "bu-1",
                domain="devtools",
                category="cli_tool",
                evidence_signals=["sig-1"],
                status="approved",
            )
        )
        store.insert_evaluation(_evaluation("bu-1", 82.0))

    result = max_opportunity_heatmap()

    assert isinstance(result, list)
    assert len(result) == 1
    bucket = result[0]
    assert bucket["domain"] == "devtools"
    assert bucket["idea_category"] == "cli_tool"
    assert bucket["evidence_density"] == 35.0
    assert bucket["freshness_signal"] == 100.0
    assert bucket["opportunity_score"] == 77.5
    assert bucket["reasons"] == [
        "average evaluated score 82.0",
        "1 signal(s) and 0 insight(s) support 1 idea(s)",
        "newest evidence fetched at 2026-04-20T00:00:00+00:00",
        "1 approved or published idea(s)",
    ]


def test_max_opportunity_heatmap_passes_filters_to_analysis(mcp_db, monkeypatch) -> None:
    captured = {}

    def fake_build_opportunity_heatmap(store, *, domain, min_signals, limit):
        captured["store"] = store
        captured["domain"] = domain
        captured["min_signals"] = min_signals
        captured["limit"] = limit
        return [{"domain": "fintech", "idea_category": "application"}]

    monkeypatch.setattr(
        "max.server.mcp_tools.build_opportunity_heatmap",
        fake_build_opportunity_heatmap,
    )

    result = max_opportunity_heatmap(domain="fintech", min_signals=3, limit=25)

    assert result == [{"domain": "fintech", "idea_category": "application"}]
    assert isinstance(captured["store"], Store)
    assert captured["domain"] == "fintech"
    assert captured["min_signals"] == 3
    assert captured["limit"] == 25


def test_max_opportunity_heatmap_invalid_min_signals_returns_validation_error(mcp_db) -> None:
    result = max_opportunity_heatmap(min_signals=-1)

    assert result["error"] == "min_signals must be non-negative"
    assert result["code"] == 400
    assert result["details"] == {
        "field": "min_signals",
        "expected": "integer >= 0",
        "actual": "-1",
    }


def test_max_opportunity_heatmap_invalid_limit_returns_validation_error(mcp_db) -> None:
    result = max_opportunity_heatmap(limit=0)

    assert result["error"] == "limit must be at least 1"
    assert result["code"] == 400
    assert result["details"] == {
        "field": "limit",
        "expected": "integer >= 1",
        "actual": "0",
    }


def test_opportunity_heatmap_resource_returns_default_json(mcp_db, monkeypatch) -> None:
    monkeypatch.setattr(
        "max.server.mcp_tools.max_opportunity_heatmap",
        lambda: [{"domain": "devtools", "idea_category": "cli_tool"}],
    )

    assert json.loads(opportunity_heatmap_detail()) == [
        {"domain": "devtools", "idea_category": "cli_tool"}
    ]


def test_create_mcp_server_registers_opportunity_heatmap_tool_and_resource(monkeypatch) -> None:
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

    assert "max_opportunity_heatmap" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["opportunities://heatmap"]
        == "opportunity_heatmap_detail"
    )
