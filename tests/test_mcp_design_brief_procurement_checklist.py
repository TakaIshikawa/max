from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_procurement_checklist import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_procurement_checklist_detail,
    get_design_brief_procurement_checklist,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_procurement_checklist_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_procurement_checklist.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_procurement_checklist_brief_id(mcp_procurement_checklist_db) -> str:
    store = Store(db_path=mcp_procurement_checklist_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-procurement-lead",
            title="Procurement Checklist MCP Lead",
            one_liner="Expose procurement readiness over MCP.",
            category="application",
            problem="Enterprise buyers need procurement artifacts before adoption.",
            solution="Return deterministic procurement checklist JSON and Markdown.",
            value_proposition="Reduce approval friction for organizational buyers.",
            specific_user="operations manager",
            buyer="VP of Operations",
            workflow_context="enterprise workflow rollout with customer data",
            current_workaround="manual vendor review documents",
            why_now="Design brief procurement checklist exports already exist.",
            validation_plan="Run procurement review with two pilot buyers.",
            first_10_customers="mid-market operations teams with formal procurement",
            domain_risks=[
                "Security and privacy review may delay customer data access.",
                "Budget owner may differ from the workflow sponsor.",
            ],
            evidence_rationale="Signals show budget, compliance, and procurement readiness gaps.",
            evidence_signals=["sig-procurement-budget", "sig-procurement-market"],
            inspiring_insights=["ins-procurement"],
            tech_approach="FastAPI and persisted checklist generation with audit-friendly JSON.",
            suggested_stack={"language": "python", "framework": "fastapi"},
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-procurement-support",
            title="Procurement Checklist MCP Support",
            one_liner="Keep procurement evidence traceable.",
            category="application",
            problem="Procurement handoffs lose source evidence.",
            solution="Trace checklist tasks back to source ideas and evidence signals.",
            value_proposition="Keep buyer review packages auditable.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="procurement package review",
            validation_plan="Compare MCP JSON and Markdown procurement output.",
            first_10_customers="platform teams with formal vendor review",
            domain_risks=["Legal review can block customer data usage."],
            evidence_rationale="Operators need evidence-linked procurement decisions.",
            evidence_signals=["sig-procurement-ops"],
            inspiring_insights=["ins-procurement-traceability"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)

        return store.insert_design_brief(
            ProjectBrief(
                title="Procurement Checklist MCP Brief",
                domain="developer-tools",
                theme="procurement-readiness",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=86.0,
                why_this_now="MCP clients need the same procurement artifact as REST clients.",
                merged_product_concept=(
                    "A procurement checklist export for persisted design briefs."
                ),
                synthesis_rationale=(
                    "Connects buyer, budget, compliance, support, and validation readiness."
                ),
                mvp_scope=["JSON procurement checklist", "Markdown procurement checklist"],
                first_milestones=["Return procurement checklist JSON"],
                validation_plan="Confirm procurement checklist traceability with budget owners.",
                risks=["Legal review is required before customer workflow data is used."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_procurement_checklist_json(
    seeded_procurement_checklist_brief_id,
) -> None:
    result = get_design_brief_procurement_checklist(
        seeded_procurement_checklist_brief_id
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.procurement_checklist"
    assert result["design_brief"]["id"] == seeded_procurement_checklist_brief_id
    assert result["design_brief"]["buyer"] == "VP of Operations"
    assert result["summary"]["procurement_gate"] == "ready_for_procurement_review"
    assert result["summary"]["missing_input_count"] == 0
    assert result["missing_inputs"] == []
    assert [section["id"] for section in result["sections"]] == [
        "security_review",
        "legal_privacy",
        "budget_owner",
        "vendor_evaluation",
        "implementation_owner",
        "approval_gates",
    ]
    assert result["checklist_items"]
    assert result["approval_gates"]
    assert "sig-procurement-budget" in result["procurement_context"]["market_sizing_hints"]
    evidence_refs = {
        ref
        for idea in result["source_ideas"]
        for ref in [*idea.get("evidence_signals", []), *idea.get("inspiring_insights", [])]
    }
    assert evidence_refs >= {
        "sig-procurement-budget",
        "sig-procurement-market",
        "ins-procurement",
    }


def test_get_design_brief_procurement_checklist_markdown(
    seeded_procurement_checklist_brief_id,
) -> None:
    result = get_design_brief_procurement_checklist(
        seeded_procurement_checklist_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_procurement_checklist_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith(
        "# Procurement Checklist: Procurement Checklist MCP Brief"
    )
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Security Review" in result["markdown"]
    assert "## Budget Owner" in result["markdown"]
    assert "## Missing Inputs" in result["markdown"]
    assert "## Recommended Next Actions" in result["markdown"]


def test_get_design_brief_procurement_checklist_not_found(
    mcp_procurement_checklist_db,
) -> None:
    result = get_design_brief_procurement_checklist("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_design_brief_procurement_checklist_resource(
    seeded_procurement_checklist_brief_id,
) -> None:
    result = json.loads(
        design_brief_procurement_checklist_detail(seeded_procurement_checklist_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_procurement_checklist_brief_id
    assert result["sections"]
    assert result["summary"]["procurement_gate"] == "ready_for_procurement_review"


def test_create_mcp_server_registers_procurement_checklist_tool(monkeypatch) -> None:
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

    assert "get_design_brief_procurement_checklist" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-procurement-checklist://{brief_id}"]
        == "design_brief_procurement_checklist_detail"
    )
