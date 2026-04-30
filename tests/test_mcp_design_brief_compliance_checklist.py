from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_compliance_checklist import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_compliance_checklist_detail,
    get_design_brief_compliance_checklist,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_compliance_checklist_db(tmp_path):
    db_path = str(tmp_path / "mcp_compliance_checklist.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_compliance_checklist_brief_id(mcp_compliance_checklist_db) -> str:
    store = Store(db_path=mcp_compliance_checklist_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-compliance-lead",
            title="Compliance Checklist MCP",
            one_liner="Expose compliance readiness over MCP.",
            category="application",
            problem="MCP consumers cannot retrieve design brief compliance checklists.",
            solution="Add a deterministic MCP tool and resource for compliance gates.",
            value_proposition="Make compliance readiness available to implementation agents.",
            specific_user="implementation agent",
            buyer="product engineering lead",
            workflow_context="design-to-implementation handoff with customer data",
            current_workaround="manual compliance notes",
            why_now="Design brief compliance checklist exports already exist.",
            validation_plan="Call the MCP compliance checklist tool before execution.",
            first_10_customers="internal implementation agents",
            domain_risks=["Privacy review could be skipped before customer data handling."],
            tech_approach="Python MCP server tool with authenticated access boundaries",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-compliance-support",
            title="Compliance Checklist Follow-up",
            one_liner="Preserve compliance follow-up traceability.",
            category="application",
            problem="Teams lose compliance decisions after handoff.",
            solution="Trace checklist items back to design brief source ideas.",
            value_proposition="Keep compliance evidence connected to source ideas.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="post-review audit",
            validation_plan="Compare JSON and Markdown checklist output.",
            domain_risks=["Traceability can drift."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)

        return store.insert_design_brief(
            ProjectBrief(
                title="Compliance Checklist MCP",
                domain="developer-tools",
                theme="compliance-readiness",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=84.0,
                why_this_now="Design brief compliance checklist exports already exist.",
                merged_product_concept="A compliance checklist MCP export for persisted design briefs.",
                synthesis_rationale="The MCP surface should expose every compliance gate artifact.",
                mvp_scope=["JSON compliance checklist", "Markdown compliance checklist", "MCP resource"],
                first_milestones=["Register compliance checklist tool", "Register compliance checklist resource"],
                validation_plan="Call the MCP compliance checklist tool before execution.",
                risks=["Privacy review could be skipped before customer data handling."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_compliance_checklist_json(
    seeded_compliance_checklist_brief_id,
) -> None:
    result = get_design_brief_compliance_checklist(seeded_compliance_checklist_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.compliance_checklist"
    assert result["design_brief"]["id"] == seeded_compliance_checklist_brief_id
    assert result["design_brief"]["title"] == "Compliance Checklist MCP"
    assert result["summary"]["gate"] == "ready_for_compliance_review"
    assert [section["id"] for section in result["sections"]] == [
        "security",
        "privacy",
        "accessibility",
        "data_retention",
        "launch_governance",
    ]
    assert result["checklist_items"]


def test_get_design_brief_compliance_checklist_markdown(
    seeded_compliance_checklist_brief_id,
) -> None:
    result = get_design_brief_compliance_checklist(
        seeded_compliance_checklist_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_compliance_checklist_brief_id
    assert result["format"] == "markdown"
    assert "# Compliance Checklist: Compliance Checklist MCP" in result["markdown"]
    assert "Schema: `max.design_brief.compliance_checklist.v1`" in result["markdown"]
    assert "## Security" in result["markdown"]


def test_get_design_brief_compliance_checklist_not_found(
    mcp_compliance_checklist_db,
) -> None:
    result = get_design_brief_compliance_checklist("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_compliance_checklist_invalid_format(
    seeded_compliance_checklist_brief_id,
) -> None:
    result = get_design_brief_compliance_checklist(
        seeded_compliance_checklist_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported compliance checklist format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_compliance_checklist_resource(
    seeded_compliance_checklist_brief_id,
) -> None:
    result = json.loads(
        design_brief_compliance_checklist_detail(seeded_compliance_checklist_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_compliance_checklist_brief_id
    assert result["checklist_items"]


def test_create_mcp_server_registers_compliance_checklist_tool(monkeypatch) -> None:
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

    assert "get_design_brief_compliance_checklist" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-compliance-checklist://{brief_id}"]
        == "design_brief_compliance_checklist_detail"
    )
