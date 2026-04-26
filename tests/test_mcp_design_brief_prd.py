from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_prd import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_prd_detail,
    get_design_brief_prd,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.insight import Insight, InsightCategory
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_prd_db(tmp_path):
    db_path = str(tmp_path / "mcp_prd.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_prd_brief_id(mcp_prd_db) -> str:
    store = Store(db_path=mcp_prd_db, wal_mode=True)
    try:
        store.insert_signal(
            Signal(
                id="sig-mcp-prd-problem",
                source_type=SignalSourceType.FORUM,
                source_adapter="hackernews",
                title="PRD signal",
                content="Teams need concise PRD handoffs from design briefs.",
                url="https://example.com/prd-signal",
                tags=["prd"],
                credibility=0.82,
                metadata={"signal_role": "problem"},
            )
        )
        store.insert_insight(
            Insight(
                id="ins-mcp-prd-gap",
                category=InsightCategory.GAP,
                title="PRD handoff gap",
                summary="Design brief consumers need concise implementation PRDs.",
                evidence=["sig-mcp-prd-problem"],
                confidence=0.86,
                domains=["developer-tools"],
            )
        )

        unit = BuildableUnit(
            id="bu-mcp-prd",
            title="Design Brief PRD MCP",
            one_liner="Expose concise PRDs over MCP",
            category="application",
            problem="Agents can fetch design brief artifacts but not concise PRDs.",
            solution="Build an MCP tool and resource for persisted PRD exports.",
            value_proposition="Improve handoff clarity for implementation agents.",
            specific_user="implementation agent",
            buyer="product engineering lead",
            workflow_context="agent implementation planning",
            current_workaround="manual PRD notes",
            why_now="Persisted design briefs already have PRD exports.",
            validation_plan="Call the MCP PRD tool during implementation planning.",
            domain_risks=["Markdown could drift from JSON output."],
            evidence_rationale="Source signals show handoff friction.",
            inspiring_insights=["ins-mcp-prd-gap"],
            evidence_signals=["sig-mcp-prd-problem"],
            tech_approach="Python MCP server tool",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)

        return store.insert_design_brief(
            ProjectBrief(
                title="Design Brief PRD MCP",
                domain="developer-tools",
                theme="agent-handoff",
                lead=Candidate(unit=unit),
                readiness_score=88.0,
                why_this_now="Persisted design briefs already have PRD exports.",
                merged_product_concept="A concise PRD MCP tool for persisted design briefs.",
                synthesis_rationale="A single source idea supports the handoff artifact.",
                mvp_scope=["JSON PRD tool", "Markdown PRD tool", "PRD MCP resource"],
                first_milestones=["Register PRD MCP tool", "Register PRD resource"],
                validation_plan="Call the MCP PRD tool during implementation planning.",
                risks=["Markdown could drift from JSON output."],
                source_idea_ids=[unit.id],
            )
        )
    finally:
        store.close()


def test_get_design_brief_prd_json(seeded_prd_brief_id) -> None:
    result = get_design_brief_prd(seeded_prd_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_prd_brief_id
    assert result["design_brief"]["title"] == "Design Brief PRD MCP"
    assert result["sections"]["problem"]["content"] == (
        "Agents can fetch design brief artifacts but not concise PRDs."
    )
    assert result["summary"]["section_count"] == 10


def test_get_design_brief_prd_markdown(seeded_prd_brief_id) -> None:
    result = get_design_brief_prd(seeded_prd_brief_id, format="markdown")

    assert result["id"] == seeded_prd_brief_id
    assert result["format"] == "markdown"
    assert "# PRD: Design Brief PRD MCP" in result["markdown"]
    assert "Schema: `max.design_brief.prd.v1`" in result["markdown"]
    assert "## Problem" in result["markdown"]


def test_get_design_brief_prd_not_found(mcp_prd_db) -> None:
    result = get_design_brief_prd("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_prd_invalid_format(seeded_prd_brief_id) -> None:
    result = get_design_brief_prd(seeded_prd_brief_id, format="yaml")

    assert result["error"] == "Unsupported PRD format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_prd_resource(seeded_prd_brief_id) -> None:
    result = json.loads(design_brief_prd_detail(seeded_prd_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_prd_brief_id
    assert result["sections"]["mvp_scope"]["content"] == [
        "JSON PRD tool",
        "Markdown PRD tool",
        "PRD MCP resource",
    ]


def test_create_mcp_server_registers_prd_tool(monkeypatch) -> None:
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

    assert "get_design_brief_prd" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-prd://{brief_id}"]
        == "design_brief_prd_detail"
    )
