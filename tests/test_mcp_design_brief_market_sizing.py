from __future__ import annotations

import json

import pytest

from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_market_sizing_detail,
    get_design_brief_market_sizing,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_market_db(tmp_path):
    db_path = str(tmp_path / "mcp_market.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_market_brief_id(mcp_market_db) -> str:
    store = Store(db_path=mcp_market_db, wal_mode=True)
    try:
        for signal in [
            _signal("sig-mcp-market-survey", SignalSourceType.SURVEY, "stackoverflow_survey", "market"),
            _signal("sig-mcp-market-funding", SignalSourceType.FUNDING, "github_funding", "market"),
            _signal("sig-mcp-market-forum", SignalSourceType.FORUM, "hackernews", "problem"),
        ]:
            store.insert_signal(signal)
        store.insert_insight(
            Insight(
                id="ins-mcp-market",
                category=InsightCategory.EMERGING_PATTERN,
                title="Agent release budget",
                summary="Platform teams are seeking release evidence.",
                evidence=["sig-mcp-market-survey", "sig-mcp-market-funding"],
                confidence=0.8,
                domains=["developer-tools"],
            )
        )
        unit = BuildableUnit(
            id="bu-mcp-market",
            title="Agent Workflow Guard",
            one_liner="Agent release checks for platform teams",
            category="application",
            problem="Platform teams cannot quantify agent release risk.",
            solution="A CI gate with workflow fixtures and evidence reports.",
            value_proposition="Reduce unsafe agent releases.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="agent release approval",
            why_now="Agents are entering production workflows.",
            validation_plan="Interview platform teams.",
            inspiring_insights=["ins-mcp-market"],
            evidence_signals=["sig-mcp-market-forum"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation("bu-mcp-market", 82.0))
        return store.insert_design_brief(
            ProjectBrief(
                title="Agent Workflow Guard",
                domain="developer-tools",
                theme="agent-release-safety",
                lead=Candidate(unit=unit),
                readiness_score=86.0,
                why_this_now="Agents are entering production workflows.",
                merged_product_concept="A CI release gate for agent workflow safety.",
                synthesis_rationale="Demand and risk signals point to platform teams.",
                mvp_scope=["CI fixture runner"],
                first_milestones=["Run pilot"],
                validation_plan="Interview platform teams.",
                risks=["Security urgency may not imply budget."],
                source_idea_ids=["bu-mcp-market"],
            )
        )
    finally:
        store.close()


def _signal(signal_id: str, source_type: SignalSourceType, adapter: str, role: str) -> Signal:
    return Signal(
        id=signal_id,
        source_type=source_type,
        source_adapter=adapter,
        title=f"{role.title()} evidence",
        content=f"Evidence for {role}",
        url=f"https://example.com/{signal_id}",
        tags=[role],
        credibility=0.8,
        metadata={"signal_role": role},
    )


def _evaluation(unit_id: str, score: float) -> UtilityEvaluation:
    dim = DimensionScore(value=8.0, confidence=0.7, reasoning="test")
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


def test_get_design_brief_market_sizing_json(seeded_market_brief_id) -> None:
    result = get_design_brief_market_sizing(seeded_market_brief_id)

    assert result["schema_version"] == "max.design_brief.market_sizing.v1"
    assert result["design_brief"]["id"] == seeded_market_brief_id
    assert result["segments"][0]["buyer"] == "engineering manager"
    assert result["segments"][0]["user"] == "platform engineer"
    assert result["market_hypotheses"]
    assert result["confidence"]["level"] in {"low", "medium", "high"}
    assert {ref["id"] for ref in result["evidence_references"]} == {
        "sig-mcp-market-survey",
        "sig-mcp-market-funding",
        "sig-mcp-market-forum",
    }


def test_get_design_brief_market_sizing_markdown(seeded_market_brief_id) -> None:
    result = get_design_brief_market_sizing(seeded_market_brief_id, format="markdown")

    assert result["id"] == seeded_market_brief_id
    assert result["format"] == "markdown"
    assert "# Market Sizing: Agent Workflow Guard" in result["markdown"]
    assert "## Segments" in result["markdown"]


def test_get_design_brief_market_sizing_not_found(mcp_market_db) -> None:
    result = get_design_brief_market_sizing("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_market_sizing_invalid_format(seeded_market_brief_id) -> None:
    result = get_design_brief_market_sizing(seeded_market_brief_id, format="yaml")

    assert result["error"] == "Unsupported market sizing format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_market_sizing_resource(seeded_market_brief_id) -> None:
    result = json.loads(design_brief_market_sizing_detail(seeded_market_brief_id))

    assert result["schema_version"] == "max.design_brief.market_sizing.v1"
    assert result["design_brief"]["id"] == seeded_market_brief_id
    assert result["evidence_references"]


def test_create_mcp_server_registers_market_sizing_tool(monkeypatch) -> None:
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

    assert "get_design_brief_market_sizing" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-market-sizing://{brief_id}"]
        == "design_brief_market_sizing_detail"
    )
