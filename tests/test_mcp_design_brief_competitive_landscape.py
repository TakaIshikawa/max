from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_competitive_landscape import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_competitive_landscape_detail,
    get_design_brief_competitive_landscape,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.evaluation import DimensionScore, UtilityEvaluation


@pytest.fixture
def mcp_competitive_db(tmp_path):
    db_path = str(tmp_path / "mcp_competitive.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_competitive_brief_id(mcp_competitive_db) -> str:
    store = Store(db_path=mcp_competitive_db, wal_mode=True)
    try:
        unit = BuildableUnit(
            id="bu-mcp-competitive",
            title="Competitive Handoff",
            one_liner="Competitive landscape source idea",
            category="application",
            problem="Design brief consumers need competitor context before handoff.",
            solution="Return stored prior-art clusters and differentiation guidance.",
            value_proposition="Improve design handoff positioning.",
            specific_user="product engineer",
            buyer="product lead",
            workflow_context="design brief implementation planning",
            validation_plan="Review with product leads.",
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(unit)
        store.insert_evaluation(_evaluation(unit.id))
        store.insert_prior_art_match(
            unit.id,
            {
                "source": "github",
                "title": "existing-brief-landscape",
                "url": "https://github.com/example/existing-brief-landscape",
                "description": "Stored prior-art record for competitive landscape handoff.",
                "relevance_score": 0.86,
                "match_signals": {"stars": 54},
                "search_query": "design brief competitive landscape",
            },
        )
        store.update_prior_art_status(unit.id, "weak_match")
        return store.insert_design_brief(
            ProjectBrief(
                title="Competitive Landscape MCP Brief",
                domain="developer-tools",
                theme="competitive-handoff",
                lead=Candidate(unit=unit),
                readiness_score=80.0,
                why_this_now="Design briefs need positioning before implementation.",
                merged_product_concept="A deterministic competitive landscape MCP tool.",
                synthesis_rationale="Single source idea for MCP handoff.",
                mvp_scope=["Competitive landscape MCP endpoint"],
                first_milestones=["Return stored prior-art clusters"],
                validation_plan="Call the MCP tool in implementation planning.",
                risks=["Competitor data may be sparse."],
                source_idea_ids=[unit.id],
            )
        )
    finally:
        store.close()


def _evaluation(unit_id: str) -> UtilityEvaluation:
    dim = DimensionScore(value=7.0, confidence=0.7, reasoning="seeded")
    return UtilityEvaluation(
        buildable_unit_id=unit_id,
        pain_severity=dim,
        addressable_scale=dim,
        build_effort=dim,
        composability=dim,
        competitive_density=DimensionScore(value=5.0, confidence=0.7, reasoning="stored prior art"),
        timing_fit=dim,
        compounding_value=dim,
        overall_score=76.0,
        strengths=["handoff-ready"],
        weaknesses=["competition exists"],
        recommendation="yes",
        weights_used={"competitive_density": 0.1},
    )


def test_get_design_brief_competitive_landscape_json(seeded_competitive_brief_id) -> None:
    result = get_design_brief_competitive_landscape(seeded_competitive_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_competitive_brief_id
    assert result["status"] == "ready"
    assert result["summary"]["prior_art_record_count"] == 1
    assert result["competitor_clusters"][0]["top_competitors"][0]["title"] == "existing-brief-landscape"
    assert result["recommended_positioning"]


def test_get_design_brief_competitive_landscape_markdown(seeded_competitive_brief_id) -> None:
    result = get_design_brief_competitive_landscape(seeded_competitive_brief_id, format="markdown")

    assert result["id"] == seeded_competitive_brief_id
    assert result["format"] == "markdown"
    assert "# Competitive Landscape: Competitive Landscape MCP Brief" in result["markdown"]
    assert "Schema: `max.design_brief.competitive_landscape.v1`" in result["markdown"]


def test_get_design_brief_competitive_landscape_not_found(mcp_competitive_db) -> None:
    result = get_design_brief_competitive_landscape("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_competitive_landscape_invalid_format(seeded_competitive_brief_id) -> None:
    result = get_design_brief_competitive_landscape(seeded_competitive_brief_id, format="yaml")

    assert result["error"] == "Unsupported competitive landscape format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_competitive_landscape_resource(seeded_competitive_brief_id) -> None:
    result = json.loads(design_brief_competitive_landscape_detail(seeded_competitive_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_competitive_brief_id
    assert result["competitor_clusters"]


def test_create_mcp_server_registers_competitive_landscape_tool(monkeypatch) -> None:
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

    assert "get_design_brief_competitive_landscape" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-competitive-landscapes://{brief_id}"]
        == "design_brief_competitive_landscape_detail"
    )
