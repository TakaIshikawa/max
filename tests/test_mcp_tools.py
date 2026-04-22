"""Tests for MCP tools (calling tool functions directly)."""

from __future__ import annotations

import pytest

from max.analysis.portfolio_synthesis import build_candidates, synthesize_project_briefs
from max.server.mcp_tools import (
    contribute_idea,
    contribute_signal,
    evidence_chain_detail,
    get_design_brief,
    get_design_brief_markdown,
    get_evidence_chain,
    get_idea,
    get_stats,
    list_design_briefs,
    search_ideas,
    set_schedule,
    set_scheduler_ref,
    set_store_factory,
)
from max.server.scheduler import Scheduler
from max.store.db import Store
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
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


@pytest.fixture
def seeded_evidence_chain_db(mcp_db):
    """DB pre-populated with an idea, insight, transitive signal, and direct signal."""
    store = Store(db_path=mcp_db, wal_mode=True)

    insight_signal = Signal(
        id="sig-chain001",
        source_type=SignalSourceType.FORUM,
        source_adapter="hn",
        title="Insight Signal",
        content="Evidence that supports the insight",
        url="https://example.com/insight-signal",
        tags=["mcp"],
        credibility=0.8,
        metadata={"signal_role": "problem"},
    )
    direct_signal = Signal(
        id="sig-chain002",
        source_type=SignalSourceType.REGISTRY,
        source_adapter="npm",
        title="Direct Signal",
        content="Direct evidence for the idea",
        url="https://example.com/direct-signal",
        tags=["registry"],
        credibility=0.7,
    )
    store.insert_signal(insight_signal)
    store.insert_signal(direct_signal)

    insight = Insight(
        id="ins-chain001",
        category=InsightCategory.GAP,
        title="Testing Gap",
        summary="MCP tools need better testing.",
        evidence=["sig-chain001"],
        confidence=0.9,
        domains=["developer-tools"],
    )
    store.insert_insight(insight)

    unit = BuildableUnit(
        id="bu-chain001",
        title="Evidence Chain Idea",
        one_liner="Expose evidence graph",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Evidence is hard to inspect",
        solution="Return a graph",
        value_proposition="Traceable ideas",
        inspiring_insights=["ins-chain001"],
        evidence_signals=["sig-chain002"],
    )
    store.insert_buildable_unit(unit)
    store.close()
    return mcp_db


@pytest.fixture
def seeded_design_brief_db(mcp_db):
    """DB pre-populated with one persisted design brief."""
    store = Store(db_path=mcp_db, wal_mode=True)

    first = BuildableUnit(
        id="bu-brief001",
        title="MCP Design Brief",
        one_liner="A test design brief for MCP",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Design handoffs lack context",
        solution="Persist synthesized briefs",
        value_proposition="Clear implementation handoff",
        specific_user="product engineer",
        buyer="engineering manager",
        workflow_context="MCP tool browsing",
        why_now="Design brief synthesis is now persisted.",
        validation_plan="Call the MCP tools.",
        domain="developer-tools",
        status="approved",
    )
    second = BuildableUnit(
        id="bu-brief002",
        title="MCP Supporting Idea",
        one_liner="Supporting idea for MCP design brief",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Supporting context is hard to find",
        solution="Attach source relationships",
        value_proposition="Better handoffs",
        specific_user="product engineer",
        buyer="engineering manager",
        workflow_context="MCP tool browsing",
        why_now="Design brief synthesis is now persisted.",
        validation_plan="Call the MCP tools.",
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(first)
    store.insert_buildable_unit(second)

    def _score(val):
        return DimensionScore(value=val, confidence=0.7, reasoning="test")

    evaluations = {}
    for unit_id, score in [("bu-brief001", 75.0), ("bu-brief002", 70.0)]:
        evaluation = UtilityEvaluation(
            buildable_unit_id=unit_id,
            pain_severity=_score(7.0),
            addressable_scale=_score(7.0),
            build_effort=_score(8.0),
            composability=_score(7.0),
            competitive_density=_score(7.0),
            timing_fit=_score(7.0),
            compounding_value=_score(7.0),
            overall_score=score,
            strengths=["Testable"],
            weaknesses=["Narrow scope"],
            recommendation="yes",
            weights_used={"pain_severity": 0.20},
        )
        store.insert_evaluation(evaluation)
        evaluations[unit_id] = evaluation

    candidates = build_candidates(
        [first, second],
        evaluations=evaluations,
        feedback={"bu-brief001": {"approval_score": 8}, "bu-brief002": {"approval_score": 6}},
    )
    brief_id = store.insert_design_brief(synthesize_project_briefs(candidates, top=1)[0])
    store.close()
    return brief_id


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


def test_get_evidence_chain_graph(seeded_evidence_chain_db):
    result = get_evidence_chain(id="bu-chain001")

    assert result["idea"]["id"] == "bu-chain001"
    assert [ins["id"] for ins in result["insights"]] == ["ins-chain001"]
    assert {sig["id"] for sig in result["signals"]} == {"sig-chain001", "sig-chain002"}
    assert {
        (edge["source"], edge["target"], edge["type"])
        for edge in result["edges"]
    } == {
        ("bu-chain001", "ins-chain001", "inspired_by"),
        ("ins-chain001", "sig-chain001", "supported_by"),
        ("bu-chain001", "sig-chain002", "direct_evidence"),
    }


def test_get_evidence_chain_not_found(mcp_db):
    result = get_evidence_chain(id="missing")
    assert result == {"error": "Idea not found: missing"}


def test_evidence_chain_resource(seeded_evidence_chain_db):
    result = evidence_chain_detail("bu-chain001")
    assert '"idea": {' in result
    assert '"type": "direct_evidence"' in result


def test_list_design_briefs(seeded_design_brief_db):
    result = list_design_briefs()
    assert len(result) == 1
    assert result[0]["id"] == seeded_design_brief_db
    assert result[0]["title"] == "MCP Design Brief"


def test_list_design_briefs_filters(seeded_design_brief_db):
    assert len(list_design_briefs(domain="developer-tools")) == 1
    assert list_design_briefs(domain="healthcare") == []
    assert len(list_design_briefs(status="candidate")) == 1
    assert list_design_briefs(status="designing") == []


def test_get_design_brief_found(seeded_design_brief_db):
    result = get_design_brief(seeded_design_brief_db)
    assert result["id"] == seeded_design_brief_db
    assert result["lead_idea_id"] == "bu-brief001"
    assert result["source_idea_ids"] == ["bu-brief001", "bu-brief002"]


def test_get_design_brief_not_found(mcp_db):
    result = get_design_brief("dbf-missing")
    assert result == {"error": "Design brief not found: dbf-missing"}


def test_get_design_brief_markdown(seeded_design_brief_db):
    result = get_design_brief_markdown(seeded_design_brief_db)
    assert result["id"] == seeded_design_brief_db
    assert "# MCP Design Brief" in result["markdown"]
    assert "### MVP Scope" in result["markdown"]


def test_get_design_brief_markdown_not_found(mcp_db):
    result = get_design_brief_markdown("dbf-missing")
    assert result == {"error": "Design brief not found: dbf-missing"}


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


def test_set_schedule_pipeline_config():
    scheduler = Scheduler(interval_seconds=3600, enabled=True)
    set_scheduler_ref(scheduler)
    try:
        result = set_schedule(
            profile="devtools",
            include_all=True,
            signal_limit=45,
            min_score=62.5,
            weight_profile="quick_wins",
            ideation_mode="refinement",
            quality_loop_enabled=True,
        )
    finally:
        set_scheduler_ref(None)

    assert result["profile"] == "devtools"
    assert result["include_all"] is True
    assert result["pipeline_config"]["signal_limit"] == 45
    assert result["pipeline_config"]["min_score"] == 62.5
    assert result["pipeline_config"]["weight_profile"] == "quick_wins"
    assert result["pipeline_config"]["ideation_mode"] == "refinement"
    assert result["pipeline_config"]["quality_loop_enabled"] is True
