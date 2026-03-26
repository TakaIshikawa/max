"""Tests for MCP tools (calling tool functions directly)."""

from __future__ import annotations

import pytest

from max.server.mcp_tools import (
    contribute_idea,
    contribute_signal,
    get_idea,
    get_spec,
    get_stats,
    search_ideas,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_db(tmp_path):
    """Create temp DB and configure mcp_tools to use it."""
    db_path = str(tmp_path / "test_mcp.db")
    # Initialize schema
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    # Reset to default
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_mcp_db(mcp_db):
    """DB pre-populated with test data."""
    store = Store(db_path=mcp_db, wal_mode=True)

    signal = Signal(
        id="sig-mcp001",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="MCP Test Signal",
        content="Test content for MCP",
        url="https://example.com/mcp-test",
        tags=["mcp"],
    )
    store.insert_signal(signal)

    unit = BuildableUnit(
        id="bu-mcp001",
        title="MCP Test Idea",
        one_liner="A test idea for MCP testing",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Testing MCP tools",
        solution="Write unit tests",
        value_proposition="Reliable MCP tools",
    )
    store.insert_buildable_unit(unit)

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    evaluation = UtilityEvaluation(
        buildable_unit_id="bu-mcp001",
        pain_severity=_score(8.0),
        addressable_scale=_score(7.0),
        build_effort=_score(7.5),
        composability=_score(8.5),
        competitive_density=_score(9.0),
        timing_fit=_score(8.0),
        compounding_value=_score(7.0),
        overall_score=78.0,
        strengths=["Testable"],
        weaknesses=["Narrow scope"],
        recommendation="yes",
        weights_used={"pain_severity": 0.20},
    )
    store.insert_evaluation(evaluation)
    store.close()
    return mcp_db


def test_search_ideas_empty(mcp_db):
    result = search_ideas()
    assert result == []


def test_search_ideas_with_data(seeded_mcp_db):
    result = search_ideas()
    assert len(result) == 1
    assert result[0]["id"] == "bu-mcp001"
    assert result[0]["score"] == 78.0


def test_search_ideas_filter_category(seeded_mcp_db):
    result = search_ideas(category="cli_tool")
    assert len(result) == 1

    result = search_ideas(category="library")
    assert len(result) == 0


def test_search_ideas_filter_query(seeded_mcp_db):
    result = search_ideas(query="MCP Test")
    assert len(result) == 1

    result = search_ideas(query="nonexistent")
    assert len(result) == 0


def test_search_ideas_filter_min_score(seeded_mcp_db):
    result = search_ideas(min_score=50.0)
    assert len(result) == 1

    result = search_ideas(min_score=90.0)
    assert len(result) == 0


def test_get_idea_found(seeded_mcp_db):
    result = get_idea(id="bu-mcp001")
    assert result["title"] == "MCP Test Idea"
    assert result["evaluation"]["overall_score"] == 78.0


def test_get_idea_not_found(mcp_db):
    result = get_idea(id="nonexistent")
    assert "error" in result


def test_contribute_signal(mcp_db):
    result = contribute_signal(
        title="Test Signal via MCP",
        content="Some content",
        url="https://example.com/mcp-contributed",
    )
    assert result["status"] == "created"
    assert result["id"].startswith("sig-")


def test_contribute_idea(mcp_db):
    result = contribute_idea(
        title="Test Idea via MCP",
        problem="Need testing",
        solution="Test via MCP tools",
    )
    assert result["status"] == "draft"
    assert result["id"].startswith("bu-")


def test_get_stats_empty(mcp_db):
    result = get_stats()
    assert result["signals_count"] == 0
    assert result["ideas_count"] == 0
    assert result["avg_score"] is None


def test_get_stats_seeded(seeded_mcp_db):
    result = get_stats()
    assert result["signals_count"] == 1
    assert result["ideas_count"] == 1
    assert result["avg_score"] == 78.0


def test_get_spec_not_found(mcp_db):
    result = get_spec(id="nonexistent")
    assert "error" in result
