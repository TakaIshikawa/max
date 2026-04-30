from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_technical_feasibility import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_technical_feasibility_detail,
    get_design_brief_technical_feasibility,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_technical_feasibility_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_technical_feasibility.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_technical_feasibility_brief_id(mcp_technical_feasibility_db) -> str:
    store = Store(db_path=mcp_technical_feasibility_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-technical-feasibility-lead",
            title="Technical Feasibility MCP Lead",
            one_liner="Expose design brief technical feasibility over MCP.",
            category="application",
            problem="Agents cannot inspect implementation constraints before tact specs.",
            solution="Return structured feasibility reports and Markdown exports from MCP.",
            value_proposition="Make architecture and integration risk visible before build planning.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="GitHub API and Slack workflow planning",
            current_workaround="manual architecture review notes",
            why_now="REST already exposes technical feasibility for persisted design briefs.",
            validation_plan="Review generated feasibility reports with implementation leads.",
            domain_risks=["External API security and credential handling can delay delivery."],
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-technical-feasibility-support",
            title="Technical Feasibility MCP Support",
            one_liner="Surface data and integration assumptions to agents.",
            category="application",
            problem="Spec authors miss early data dependencies.",
            solution="List API, webhook, telemetry, and workflow dependencies.",
            value_proposition="Reduce late-stage feasibility surprises.",
            specific_user="technical product manager",
            buyer="product lead",
            workflow_context="implementation constraint review",
            domain_risks=["PII and compliance requirements need security review."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)
        return store.insert_design_brief(
            ProjectBrief(
                title="Technical Feasibility MCP Brief",
                domain="developer-tools",
                theme="technical-feasibility-mcp-export",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=86.0,
                why_this_now="MCP access lets agents inspect feasibility before drafting specs.",
                merged_product_concept=(
                    "A GitHub API and Slack workflow service that exposes technical "
                    "feasibility, telemetry, and implementation constraints."
                ),
                synthesis_rationale="Covers pre-build architecture handoff for persisted briefs.",
                mvp_scope=[
                    "Technical feasibility JSON MCP tool",
                    "Technical feasibility Markdown MCP tool",
                ],
                first_milestones=["Return technical feasibility JSON from MCP"],
                validation_plan="Confirm engineering leads can use the feasibility report.",
                risks=["External API security and credential handling can delay delivery."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_technical_feasibility_json(
    seeded_technical_feasibility_brief_id,
) -> None:
    result = get_design_brief_technical_feasibility(seeded_technical_feasibility_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["source"]["id"] == seeded_technical_feasibility_brief_id
    assert result["design_brief"]["id"] == seeded_technical_feasibility_brief_id
    assert result["design_brief"]["title"] == "Technical Feasibility MCP Brief"
    assert result["design_brief"]["source_idea_ids"] == [
        "bu-mcp-technical-feasibility-lead",
        "bu-mcp-technical-feasibility-support",
    ]
    assert result["feasibility_verdict"]["verdict"] in {
        "proceed",
        "spike_required",
        "needs_decomposition",
    }
    assert [item["id"] for item in result["architecture_assumptions"]] == ["A1", "A2", "A3"]
    assert {item["type"] for item in result["integration_surface"]} >= {
        "application_surface",
        "external_api",
        "developer_platform",
        "messaging",
    }
    assert result["data_dependencies"]
    assert result["recommended_spike_plan"]


def test_get_design_brief_technical_feasibility_markdown(
    seeded_technical_feasibility_brief_id,
) -> None:
    result = get_design_brief_technical_feasibility(
        seeded_technical_feasibility_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_technical_feasibility_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith(
        "# Technical Feasibility: Technical Feasibility MCP Brief"
    )
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Feasibility Verdict" in result["markdown"]
    assert "## Architecture Assumptions" in result["markdown"]
    assert "## Integration Surface" in result["markdown"]
    assert "## Recommended Spike Plan" in result["markdown"]


def test_get_design_brief_technical_feasibility_not_found(
    mcp_technical_feasibility_db,
) -> None:
    result = get_design_brief_technical_feasibility("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_technical_feasibility_invalid_format(
    seeded_technical_feasibility_brief_id,
) -> None:
    result = get_design_brief_technical_feasibility(
        seeded_technical_feasibility_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported technical feasibility format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_technical_feasibility_resource(
    seeded_technical_feasibility_brief_id,
) -> None:
    result = json.loads(
        design_brief_technical_feasibility_detail(seeded_technical_feasibility_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["source"]["id"] == seeded_technical_feasibility_brief_id
    assert result["design_brief"]["title"] == "Technical Feasibility MCP Brief"
    assert result["feasibility_verdict"]
    assert result["recommended_spike_plan"]


def test_create_mcp_server_registers_technical_feasibility_tool(monkeypatch) -> None:
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

    assert "get_design_brief_technical_feasibility" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-technical-feasibility://{brief_id}"]
        == "design_brief_technical_feasibility_detail"
    )
