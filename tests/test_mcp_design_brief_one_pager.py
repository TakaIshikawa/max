"""Tests for design brief one-pager exposure through MCP."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_one_pager import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server import mcp_tools
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_one_pager_detail,
    get_design_brief_one_pager,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit
from max.types.signal import Signal, SignalSourceType


@pytest.fixture
def mcp_one_pager_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_one_pager.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_one_pager_brief_id(mcp_one_pager_db) -> str:
    store = Store(db_path=mcp_one_pager_db, wal_mode=True)
    try:
        return _seed_design_brief(store)
    finally:
        store.close()


def test_get_design_brief_one_pager_returns_seeded_handoff_fields(
    seeded_one_pager_brief_id,
) -> None:
    result = get_design_brief_one_pager(seeded_one_pager_brief_id)

    assert result["id"] == seeded_one_pager_brief_id
    assert result["format"] == "json"
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_one_pager_brief_id
    assert result["brief_summary"]["title"] == "MCP One-Pager Brief"
    assert result["brief_summary"]["evidence_count"] >= 2
    assert result["buyer"] == "VP of Product Operations"
    assert result["workflow"] == "weekly portfolio design review"
    assert result["concept"] == "A deterministic one-page export for design brief handoffs."
    assert result["problem"] == "Stakeholders need a compact design brief summary."
    assert result["solution"] == "A deterministic one-page export for design brief handoffs."
    assert result["differentiation"] == "Compress review context without losing traceability."
    assert result["validation_plan"] == "Review the one-pager with product and delivery owners."
    assert result["risks"][0]["title"] == "Traceability can be missed in handoffs"
    assert result["source_ids"] == ["bu-mcp-one-pager-lead"]
    assert result["source_idea_ids"] == ["bu-mcp-one-pager-lead"]
    assert result["source_idea_traceability"] == [
        {
            "idea_id": "bu-mcp-one-pager-lead",
            "role": "lead",
            "rank": 0,
            "title": "MCP One-Pager Lead",
            "source_fields": [
                "buyer",
                "problem",
                "solution",
                "value_proposition",
                "validation_plan",
                "domain_risks",
            ],
            "buyer": "VP of Product Operations",
            "problem": "Stakeholders need a compact design brief summary.",
            "solution": "Expose the existing one-pager as an MCP tool.",
            "differentiation": "Compress review context without losing traceability.",
            "validation_plan": "Review with product and delivery owners.",
            "risks": ["Traceability can be missed in handoffs."],
        }
    ]
    assert json.loads(result["rendered"])["design_brief"]["id"] == seeded_one_pager_brief_id


def test_get_design_brief_one_pager_markdown(seeded_one_pager_brief_id) -> None:
    result = get_design_brief_one_pager(seeded_one_pager_brief_id, format="markdown")

    assert result["id"] == seeded_one_pager_brief_id
    assert result["format"] == "markdown"
    assert result["one_pager"]["schema_version"] == SCHEMA_VERSION
    assert result["buyer"] == "VP of Product Operations"
    assert "# One-Pager: MCP One-Pager Brief" in result["markdown"]
    assert "**Problem**: Stakeholders need a compact design brief summary." in result["markdown"]
    assert "**Source idea IDs**: bu-mcp-one-pager-lead" in result["markdown"]


def test_get_design_brief_one_pager_not_found(mcp_one_pager_db) -> None:
    result = get_design_brief_one_pager("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_one_pager_invalid_format(seeded_one_pager_brief_id) -> None:
    result = get_design_brief_one_pager(seeded_one_pager_brief_id, format="yaml")

    assert result["error"] == "Unsupported design brief one-pager format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_one_pager_resource(seeded_one_pager_brief_id) -> None:
    result = json.loads(design_brief_one_pager_detail(seeded_one_pager_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_one_pager_brief_id
    assert result["source_idea_traceability"][0]["idea_id"] == "bu-mcp-one-pager-lead"


def test_create_mcp_server_registers_one_pager_tool(monkeypatch) -> None:
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

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_design_brief_one_pager" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-one-pagers://{brief_id}"]
        == "design_brief_one_pager_detail"
    )


def _seed_design_brief(store: Store) -> str:
    store.insert_signal(
        Signal(
            id="sig-mcp-one-pager-problem",
            source_type=SignalSourceType.FORUM,
            source_adapter="test",
            title="One-pager handoff demand",
            content="Agents and stakeholders need concise design brief handoffs.",
            url="https://example.com/mcp-one-pager",
            tags=["problem"],
            credibility=0.8,
            metadata={"signal_role": "problem"},
        )
    )
    lead = BuildableUnit(
        id="bu-mcp-one-pager-lead",
        title="MCP One-Pager Lead",
        one_liner="Expose one-page design brief handoffs",
        category="application",
        problem="Stakeholders need a compact design brief summary.",
        solution="Expose the existing one-pager as an MCP tool.",
        value_proposition="Compress review context without losing traceability.",
        specific_user="portfolio reviewer",
        buyer="VP of Product Operations",
        workflow_context="weekly portfolio design review",
        current_workaround="manual summary notes",
        why_now="Design brief one-pagers already exist over the API.",
        validation_plan="Review with product and delivery owners.",
        first_10_customers="internal product and delivery teams",
        domain_risks=["Traceability can be missed in handoffs."],
        evidence_rationale="Seed evidence shows handoff friction.",
        evidence_signals=["sig-mcp-one-pager-problem"],
        tech_approach="FastMCP tool wrapping the deterministic one-pager builder.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="MCP One-Pager Brief",
            domain="developer-tools",
            theme="stakeholder-summary",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=82.0,
            why_this_now="Agents need a concise artifact for handoff packets.",
            merged_product_concept="A deterministic one-page export for design brief handoffs.",
            synthesis_rationale="Summarizes buyer, problem, solution, validation, and risk.",
            mvp_scope=["MCP one-pager tool", "MCP one-pager resource"],
            first_milestones=["Register MCP one-pager export"],
            validation_plan="Review the one-pager with product and delivery owners.",
            risks=["Traceability can be missed in handoffs."],
            source_idea_ids=[lead.id],
        )
    )
