from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_okrs import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_okrs_detail,
    get_design_brief_okrs,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_okrs_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_okrs.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_okrs_brief_id(mcp_okrs_db) -> str:
    store = Store(db_path=mcp_okrs_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-okrs-lead",
            title="OKR MCP Lead",
            one_liner="Expose design brief OKRs over MCP.",
            category="application",
            problem="Planning agents cannot inspect design brief execution OKRs.",
            solution="Return structured OKRs and Markdown exports from MCP.",
            value_proposition="Make execution goals available to autonomous planning.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="design brief execution planning",
            why_now="Design brief artifacts already support downstream workflows.",
            validation_plan="Review generated OKRs with product and engineering leads.",
            domain_risks=["Security review can delay validation."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)

        return store.insert_design_brief(
            ProjectBrief(
                title="OKR MCP Brief",
                domain="developer-tools",
                theme="mcp-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=88.0,
                why_this_now="MCP access lets agents consume OKRs.",
                merged_product_concept="Expose deterministic design brief OKRs over JSON and Markdown.",
                synthesis_rationale="The OKR module creates a stable execution artifact.",
                mvp_scope=["JSON OKR MCP tool", "Markdown OKR MCP tool"],
                first_milestones=["Return structured OKRs from MCP"],
                validation_plan="Confirm the MCP payload matches the OKR renderer.",
                risks=[],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_okrs_json(seeded_okrs_brief_id) -> None:
    result = get_design_brief_okrs(seeded_okrs_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_okrs_brief_id
    assert result["design_brief"]["title"] == "OKR MCP Brief"
    assert result["summary"]["objective_count"] == 4
    assert result["summary"]["key_result_count"] == 12
    assert result["summary"]["validation_required"] is True
    assert result["objectives"][0]["id"] == "O1"
    assert result["objectives"][0]["objective"] == "Validate demand for OKR MCP Brief"
    assert result["objectives"][0]["key_results"][0] == {
        "id": "KR1",
        "metric": "Interview at least 5 platform engineer",
        "target": "5 completed interviews",
        "evidence_source": "Customer discovery notes",
    }


def test_get_design_brief_okrs_markdown(seeded_okrs_brief_id) -> None:
    result = get_design_brief_okrs(seeded_okrs_brief_id, format="markdown")

    assert result["id"] == seeded_okrs_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# OKRs: OKR MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Objectives" in result["markdown"]
    assert "### O1: Validate demand for OKR MCP Brief" in result["markdown"]


def test_get_design_brief_okrs_not_found(mcp_okrs_db) -> None:
    result = get_design_brief_okrs("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_okrs_invalid_format(seeded_okrs_brief_id) -> None:
    result = get_design_brief_okrs(seeded_okrs_brief_id, format="yaml")

    assert result["error"] == "Unsupported OKR format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_okrs_resource(seeded_okrs_brief_id) -> None:
    result = json.loads(design_brief_okrs_detail(seeded_okrs_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_okrs_brief_id
    assert result["objectives"][0]["id"] == "O1"


def test_create_mcp_server_registers_okrs_tool(monkeypatch) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name):
            self.name = name
            self.tools = {}
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn):
            self.tools[fn.__name__] = fn.__doc__
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr("max.server.mcp_tools.FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_design_brief_okrs" in FakeMCP.latest.tools
    assert "execution OKRs" in FakeMCP.latest.tools["get_design_brief_okrs"]
    assert (
        FakeMCP.latest.resources["design-brief-okrs://{brief_id}"]
        == "design_brief_okrs_detail"
    )
