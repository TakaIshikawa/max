from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_onboarding_plan import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_onboarding_plan_detail,
    get_design_brief_onboarding_plan,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_onboarding_plan_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_onboarding_plan.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_onboarding_plan_brief_id(mcp_onboarding_plan_db) -> str:
    store = Store(db_path=mcp_onboarding_plan_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-onboarding-lead",
            title="Onboarding Plan MCP Lead",
            one_liner="Expose onboarding plans for approved design briefs over MCP.",
            category="application",
            problem="Autonomous agents cannot retrieve post-sale onboarding handoff plans.",
            solution="Return deterministic customer onboarding plans as JSON and Markdown.",
            value_proposition="Turn pilot approval into repeatable customer activation.",
            specific_user="customer operations manager",
            buyer="customer success director",
            workflow_context="approved pilot onboarding",
            current_workaround="manual kickoff notes",
            why_now="MCP consumers need customer rollout artifacts alongside briefs.",
            validation_plan="Track first value, repeat setup, sponsor acceptance, and handoff.",
            domain_risks=["Privacy approval can block customer data setup."],
            evidence_signals=["sig-mcp-onboarding"],
            inspiring_insights=["customers need champion-ready onboarding"],
            domain="customer-success",
            status="approved",
        )
        store.insert_buildable_unit(lead)

        return store.insert_design_brief(
            ProjectBrief(
                title="Onboarding Plan MCP Brief",
                domain="customer-success",
                theme="post-sale-onboarding-mcp",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=88.0,
                why_this_now="Generated specs need post-sale onboarding artifacts.",
                merged_product_concept="An onboarding plan export for persisted design briefs.",
                synthesis_rationale="Connects pilot approval to customer rollout operations.",
                mvp_scope=["Onboarding plan JSON", "Onboarding plan Markdown"],
                first_milestones=["Complete guided first-value onboarding"],
                validation_plan=(
                    "Confirm customer teams can onboard a second user without concierge help."
                ),
                risks=["Privacy approval can block customer data setup."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_onboarding_plan_json(seeded_onboarding_plan_brief_id) -> None:
    first = get_design_brief_onboarding_plan(seeded_onboarding_plan_brief_id)
    second = get_design_brief_onboarding_plan(seeded_onboarding_plan_brief_id)

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.onboarding_plan"
    assert first["source"]["entity_type"] == "design_brief"
    assert first["source"]["id"] == seeded_onboarding_plan_brief_id
    assert first["design_brief"]["id"] == seeded_onboarding_plan_brief_id
    assert first["design_brief"]["title"] == "Onboarding Plan MCP Brief"
    assert first["summary"]["target_user"] == "customer operations manager"
    assert first["summary"]["buyer"] == "customer success director"
    assert [phase["id"] for phase in first["onboarding_phases"]] == [
        "phase-1",
        "phase-2",
        "phase-3",
        "phase-4",
    ]
    assert first["success_criteria"]
    assert first["owner_hints"]
    assert first["risks"]
    assert first["required_assets"]


def test_get_design_brief_onboarding_plan_markdown(
    seeded_onboarding_plan_brief_id,
) -> None:
    result = get_design_brief_onboarding_plan(
        seeded_onboarding_plan_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_onboarding_plan_brief_id
    assert result["format"] == "markdown"
    markdown = result["markdown"]
    assert markdown.startswith("# Onboarding Plan: Onboarding Plan MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{seeded_onboarding_plan_brief_id}`" in markdown
    assert "## Onboarding Phases" in markdown
    assert "### phase-1: Account Readiness" in markdown
    assert "## Success Criteria" in markdown
    assert "## Required Assets" in markdown


def test_get_design_brief_onboarding_plan_not_found(mcp_onboarding_plan_db) -> None:
    result = get_design_brief_onboarding_plan("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_onboarding_plan_invalid_format(
    seeded_onboarding_plan_brief_id,
) -> None:
    result = get_design_brief_onboarding_plan(
        seeded_onboarding_plan_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported onboarding plan format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_onboarding_plan_resource(seeded_onboarding_plan_brief_id) -> None:
    result = json.loads(design_brief_onboarding_plan_detail(seeded_onboarding_plan_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_onboarding_plan_brief_id
    assert result["onboarding_phases"]
    assert result["success_criteria"]


def test_create_mcp_server_registers_onboarding_plan_tool(monkeypatch) -> None:
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

    assert "get_design_brief_onboarding_plan" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-onboarding-plans://{brief_id}"]
        == "design_brief_onboarding_plan_detail"
    )
