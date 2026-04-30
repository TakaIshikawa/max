from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_sales_battlecard import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_sales_battlecard_detail,
    get_design_brief_sales_battlecard,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_sales_battlecard_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_sales_battlecard.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_sales_battlecard_brief_id(mcp_sales_battlecard_db) -> str:
    store = Store(db_path=mcp_sales_battlecard_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-sales-battlecard-lead",
            title="Sales Battlecard MCP Lead",
            one_liner="Expose sales battlecards over MCP.",
            category="application",
            problem=(
                "Revenue teams cannot turn design brief buyer pains into reliable "
                "discovery conversations."
            ),
            solution="Return structured battlecards and Markdown exports from MCP.",
            value_proposition=(
                "Help account teams convert design briefs into pilot-ready sales motions."
            ),
            specific_user="account executive",
            buyer="revenue leader",
            workflow_context="pilot discovery call",
            current_workaround="generic competitor comparison notes",
            why_now="Autonomous go-to-market agents need deterministic sales artifacts.",
            validation_plan="Review battlecards with account teams and validate objections.",
            domain_risks=["Security review can delay sales access."],
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-sales-battlecard-support",
            title="Sales Battlecard MCP Support",
            one_liner="Trace sales claims to source ideas.",
            category="application",
            problem="Competitive follow-up gets detached from product evidence.",
            solution="Attach source idea identifiers to each sales claim.",
            value_proposition="Keep sales handoffs auditable for agents.",
            specific_user="sales engineer",
            buyer="revenue operations lead",
            workflow_context="competitive pilot evaluation",
            current_workaround="untraceable battlecard spreadsheet",
            domain_risks=["Objections can drift without source evidence."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)
        return store.insert_design_brief(
            ProjectBrief(
                title="Sales Battlecard MCP Brief",
                domain="developer-tools",
                theme="sales-battlecard-mcp-export",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=87.0,
                why_this_now="MCP access lets agents consume sales battlecards.",
                merged_product_concept="A sales battlecard export for persisted design briefs.",
                synthesis_rationale="Covers revenue handoff after product planning.",
                mvp_scope=["Sales battlecard JSON", "Sales battlecard Markdown"],
                first_milestones=["Return sales battlecard JSON from MCP"],
                validation_plan="Confirm account teams can handle pilot objections.",
                risks=["Security review can delay sales access."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_sales_battlecard_json(
    seeded_sales_battlecard_brief_id,
) -> None:
    result = get_design_brief_sales_battlecard(seeded_sales_battlecard_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.sales_battlecard"
    assert result["design_brief"]["id"] == seeded_sales_battlecard_brief_id
    assert result["design_brief"]["title"] == "Sales Battlecard MCP Brief"
    assert result["design_brief"]["source_idea_ids"] == [
        "bu-mcp-sales-battlecard-lead",
        "bu-mcp-sales-battlecard-support",
    ]
    assert "buyer pains" in result["summary"]["primary_pain"]
    assert result["positioning"]["one_liner"] == "Expose sales battlecards over MCP."
    assert result["positioning"]["qualification_signal"] == "pilot discovery call"
    assert (
        result["positioning"]["disqualification_signal"]
        == "generic competitor comparison notes"
    )
    assert [row["id"] for row in result["objection_handling"]] == [
        "status_quo",
        "priority",
        "risk_or_trust",
    ]
    assert any(
        "current workaround" in row["objection"].lower()
        and "generic competitor comparison notes" in row["response"]
        for row in result["objection_handling"]
    )
    assert {
        row["discovery_follow_up"]
        for row in result["objection_handling"]
    } >= {
        "What happens when this workflow doubles in volume?",
        "What proof would make this safe enough for a pilot?",
    }
    assert all(
        row["source_idea_ids"]
        == ["bu-mcp-sales-battlecard-lead", "bu-mcp-sales-battlecard-support"]
        for row in result["objection_handling"]
    )
    assert all(
        proof["source_idea_ids"]
        == ["bu-mcp-sales-battlecard-lead", "bu-mcp-sales-battlecard-support"]
        for proof in result["proof_points"]
    )


def test_get_design_brief_sales_battlecard_markdown(
    seeded_sales_battlecard_brief_id,
) -> None:
    result = get_design_brief_sales_battlecard(
        seeded_sales_battlecard_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_sales_battlecard_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Sales Battlecard: Sales Battlecard MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "Source ideas: bu-mcp-sales-battlecard-lead, bu-mcp-sales-battlecard-support" in result["markdown"]
    assert "## Positioning" in result["markdown"]
    assert "## Objection Handling" in result["markdown"]
    assert "Discovery follow-up:" in result["markdown"]
    assert "generic competitor comparison notes" in result["markdown"]
    assert "## Proof Points" in result["markdown"]


def test_get_design_brief_sales_battlecard_not_found(
    mcp_sales_battlecard_db,
) -> None:
    result = get_design_brief_sales_battlecard("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_sales_battlecard_invalid_format(
    seeded_sales_battlecard_brief_id,
) -> None:
    result = get_design_brief_sales_battlecard(
        seeded_sales_battlecard_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported sales battlecard format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_sales_battlecard_resource(
    seeded_sales_battlecard_brief_id,
) -> None:
    result = json.loads(
        design_brief_sales_battlecard_detail(seeded_sales_battlecard_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_sales_battlecard_brief_id
    assert result["positioning"]
    assert result["objection_handling"]
    assert result["proof_points"]


def test_create_mcp_server_registers_sales_battlecard_tool(monkeypatch) -> None:
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

    assert "get_design_brief_sales_battlecard" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-briefs://{brief_id}/sales-battlecard"]
        == "design_brief_sales_battlecard_detail"
    )
