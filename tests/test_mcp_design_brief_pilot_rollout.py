from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_pilot_rollout import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_pilot_rollout_detail,
    get_design_brief_pilot_rollout,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_pilot_rollout_db(tmp_path):
    db_path = str(tmp_path / "mcp_pilot_rollout.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_pilot_rollout_brief_id(mcp_pilot_rollout_db) -> str:
    store = Store(db_path=mcp_pilot_rollout_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-pilot-lead",
            title="Pilot Rollout MCP",
            one_liner="Expose pilot rollout guidance over MCP.",
            category="application",
            problem="MCP consumers cannot retrieve staged rollout plans.",
            solution="Add deterministic MCP access to pilot rollout artifacts.",
            value_proposition="Make rollout readiness available to implementation agents.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="design-to-implementation handoff",
            current_workaround="manual pilot notes",
            why_now="Design brief pilot rollout exports already exist.",
            validation_plan="Call the MCP pilot rollout tool before launch.",
            first_10_customers="internal product operators",
            domain_risks=["Privacy review is required before customer workflow data is used."],
            evidence_signals=["sig-mcp-pilot"],
            inspiring_insights=["ins-mcp-pilot"],
            tech_approach="Python MCP server tool with deterministic rollout output",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)

        return store.insert_design_brief(
            ProjectBrief(
                title="Pilot Rollout MCP",
                domain="developer-tools",
                theme="pilot-rollout",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=84.0,
                why_this_now="Design brief pilot rollout exports already exist.",
                merged_product_concept="A pilot rollout MCP export for persisted design briefs.",
                synthesis_rationale="The MCP surface should expose staged rollout artifacts.",
                mvp_scope=["Pilot rollout JSON", "Pilot rollout Markdown"],
                first_milestones=["Register pilot rollout tool"],
                validation_plan="Call the MCP pilot rollout tool before launch.",
                risks=["Privacy review is required before customer workflow data is used."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_pilot_rollout_json(seeded_pilot_rollout_brief_id) -> None:
    result = get_design_brief_pilot_rollout(seeded_pilot_rollout_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.pilot_rollout"
    assert result["design_brief"]["id"] == seeded_pilot_rollout_brief_id
    assert result["design_brief"]["title"] == "Pilot Rollout MCP"
    assert result["pilot_cohort"]["target_users"] == "product operator"
    assert [phase["id"] for phase in result["rollout_phases"]] == [
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
    ]
    assert result["success_thresholds"]
    assert result["operator_tasks"]
    assert result["customer_touchpoints"]


def test_get_design_brief_pilot_rollout_markdown(
    seeded_pilot_rollout_brief_id,
) -> None:
    result = get_design_brief_pilot_rollout(
        seeded_pilot_rollout_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_pilot_rollout_brief_id
    assert result["format"] == "markdown"
    assert "# Pilot Rollout Plan: Pilot Rollout MCP" in result["markdown"]
    assert "Schema: `max.design_brief.pilot_rollout.v1`" in result["markdown"]
    assert "## Rollout Phases" in result["markdown"]


def test_get_design_brief_pilot_rollout_not_found(mcp_pilot_rollout_db) -> None:
    result = get_design_brief_pilot_rollout("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_pilot_rollout_invalid_format(
    seeded_pilot_rollout_brief_id,
) -> None:
    result = get_design_brief_pilot_rollout(
        seeded_pilot_rollout_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported pilot rollout format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_pilot_rollout_resource(seeded_pilot_rollout_brief_id) -> None:
    result = json.loads(design_brief_pilot_rollout_detail(seeded_pilot_rollout_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_pilot_rollout_brief_id
    assert result["rollout_phases"]


def test_create_mcp_server_registers_pilot_rollout_tool(monkeypatch) -> None:
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

    assert "get_design_brief_pilot_rollout" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-pilot-rollouts://{brief_id}"]
        == "design_brief_pilot_rollout_detail"
    )
