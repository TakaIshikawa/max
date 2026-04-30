from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_raci_matrix import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_raci_matrix_detail,
    get_design_brief_raci_matrix,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_raci_matrix_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_raci_matrix.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_raci_matrix_brief_id(mcp_raci_matrix_db) -> str:
    store = Store(db_path=mcp_raci_matrix_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-raci-lead",
            title="RACI Matrix MCP Lead",
            one_liner="Expose design brief RACI ownership over MCP.",
            category="application",
            problem="Agents cannot inspect ownership before implementation handoff.",
            solution="Return structured RACI matrices and Markdown exports from MCP.",
            value_proposition="Make launch and validation ownership visible before planning.",
            specific_user="platform lead",
            buyer="engineering director",
            workflow_context="internal developer platform launch readiness",
            current_workaround="manual ownership spreadsheet",
            why_now="REST already exposes RACI matrices for persisted design briefs.",
            validation_plan="Review the generated RACI matrix with launch owners.",
            domain_risks=["Support escalation ownership can delay launch readiness."],
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-raci-support",
            title="RACI Matrix MCP Support",
            one_liner="Surface accountable launch ownership to agents.",
            category="application",
            problem="Spec authors miss consulted and informed roles.",
            solution="List implementation, validation, support, and launch RACI rows.",
            value_proposition="Reduce ownership ambiguity before build execution.",
            specific_user="customer success manager",
            buyer="support director",
            workflow_context="support playbook and launch handoff",
            domain_risks=["Risk approval needs a named accountable owner."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)
        return store.insert_design_brief(
            ProjectBrief(
                title="RACI Matrix MCP Brief",
                domain="developer-tools",
                theme="raci-matrix-mcp-export",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=88.0,
                why_this_now="MCP access lets agents inspect ownership before drafting specs.",
                merged_product_concept=(
                    "A developer platform launch workflow that exposes RACI ownership, "
                    "support playbook needs, and validation accountability."
                ),
                synthesis_rationale="Covers ownership handoff for persisted design briefs.",
                mvp_scope=[
                    "RACI matrix JSON MCP tool",
                    "RACI matrix Markdown MCP tool",
                ],
                first_milestones=["Return RACI matrix JSON from MCP"],
                validation_plan="Confirm launch owners can use the RACI matrix.",
                risks=["Support escalation ownership can delay launch readiness."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_raci_matrix_json(seeded_raci_matrix_brief_id) -> None:
    result = get_design_brief_raci_matrix(seeded_raci_matrix_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.raci_matrix"
    assert result["source"]["id"] == seeded_raci_matrix_brief_id
    assert result["design_brief"]["id"] == seeded_raci_matrix_brief_id
    assert result["design_brief"]["title"] == "RACI Matrix MCP Brief"
    assert result["design_brief"]["source_idea_ids"] == [
        "bu-mcp-raci-lead",
        "bu-mcp-raci-support",
    ]
    assert result["summary"]["phase_count"] == 4
    assert result["summary"]["activity_count"] == len(result["activities"])
    assert [phase["id"] for phase in result["phases"]] == [
        "alignment",
        "implementation_handoff",
        "validation",
        "launch_readiness",
    ]
    assert [activity["id"] for activity in result["activities"]] == [
        f"DBRACI{index}" for index in range(1, 9)
    ]
    assert result["role_assignments"]
    assert result["escalation_notes"]


def test_get_design_brief_raci_matrix_markdown(seeded_raci_matrix_brief_id) -> None:
    result = get_design_brief_raci_matrix(
        seeded_raci_matrix_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_raci_matrix_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# RACI Matrix: RACI Matrix MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert f"Design brief: `{seeded_raci_matrix_brief_id}`" in result["markdown"]
    assert "## Alignment" in result["markdown"]
    assert "## Implementation Handoff" in result["markdown"]
    assert "## Validation" in result["markdown"]
    assert "## Launch Readiness" in result["markdown"]
    assert "| Activity | Responsible | Accountable | Consulted | Informed | Gaps |" in result[
        "markdown"
    ]
    assert "## Ownership Gaps" in result["markdown"]
    assert "## Escalation Notes" in result["markdown"]


def test_get_design_brief_raci_matrix_not_found(mcp_raci_matrix_db) -> None:
    result = get_design_brief_raci_matrix("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_raci_matrix_invalid_format(seeded_raci_matrix_brief_id) -> None:
    result = get_design_brief_raci_matrix(
        seeded_raci_matrix_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported RACI matrix format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_raci_matrix_resource(seeded_raci_matrix_brief_id) -> None:
    result = json.loads(design_brief_raci_matrix_detail(seeded_raci_matrix_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["source"]["id"] == seeded_raci_matrix_brief_id
    assert result["design_brief"]["title"] == "RACI Matrix MCP Brief"
    assert result["phases"]
    assert result["activities"]
    assert result["role_assignments"]


def test_create_mcp_server_registers_raci_matrix_tool(monkeypatch) -> None:
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

    assert "get_design_brief_raci_matrix" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-raci-matrices://{brief_id}"]
        == "design_brief_raci_matrix_detail"
    )
