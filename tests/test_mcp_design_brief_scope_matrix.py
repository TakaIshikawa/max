"""Tests for design brief scope matrix MCP exports."""

from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_scope_matrix import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_scope_matrix_detail,
    get_design_brief_scope_matrix,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_db(tmp_path):
    db_path = str(tmp_path / "test_mcp_scope_matrix.db")
    Store(db_path=db_path, wal_mode=True).close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_brief_id(mcp_db: str) -> str:
    with Store(db_path=mcp_db, wal_mode=True) as store:
        lead = BuildableUnit(
            id="bu-scope-mcp-lead",
            title="Scope Matrix MCP Lead",
            one_liner="Expose scope decisions to coding agents.",
            category="application",
            problem="Implementation agents cannot tell MVP from later scope.",
            solution="Publish a deterministic scope matrix over MCP.",
            value_proposition="Keep implementation work aligned to brief intent.",
            specific_user="implementation agent",
            buyer="VP of Product",
            workflow_context="pre-build scope review",
            current_workaround="manual design brief reading",
            validation_plan="Review MVP and non-goal decisions before implementation.",
            domain_risks=["Scope may expand into full roadmap automation."],
            evidence_signals=[],
            tech_approach="MCP tool over deterministic scope matrix generation.",
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Scope Matrix MCP Brief",
                domain="developer-tools",
                theme="scope-matrix",
                lead=Candidate(unit=lead),
                readiness_score=82.0,
                why_this_now="Agents need scope boundaries before implementation handoff.",
                merged_product_concept="A scope matrix artifact for persisted design briefs.",
                synthesis_rationale="Makes MVP, later, and out-of-scope work explicit.",
                mvp_scope=["JSON scope matrix MCP tool", "Markdown scope matrix MCP tool"],
                first_milestones=["Return MoSCoW buckets over MCP"],
                validation_plan="Review MVP and non-goal decisions before implementation.",
                risks=["Scope may expand into full roadmap automation."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )


def test_get_design_brief_scope_matrix_json(seeded_brief_id: str) -> None:
    result = get_design_brief_scope_matrix(seeded_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.scope_matrix"
    assert result["design_brief"]["id"] == seeded_brief_id
    assert result["design_brief"]["title"] == "Scope Matrix MCP Brief"
    assert result["summary"]["bucket_count"] == 4
    assert [item["bucket"] for item in result["items"]] == [
        "must_have",
        "should_have",
        "could_have",
        "wont_have_now",
    ]


def test_get_design_brief_scope_matrix_markdown(seeded_brief_id: str) -> None:
    result = get_design_brief_scope_matrix(seeded_brief_id, format="markdown")

    assert result["id"] == seeded_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Scope Decision Matrix: Scope Matrix MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Must Have" in result["markdown"]
    assert "## Won't Have Now" in result["markdown"]


def test_get_design_brief_scope_matrix_missing_brief(mcp_db: str) -> None:
    result = get_design_brief_scope_matrix("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_scope_matrix_invalid_format(seeded_brief_id: str) -> None:
    result = get_design_brief_scope_matrix(seeded_brief_id, format="yaml")

    assert result["error"] == "Unsupported scope matrix format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_scope_matrix_resource(seeded_brief_id: str) -> None:
    result = json.loads(design_brief_scope_matrix_detail(seeded_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_brief_id


def test_design_brief_scope_matrix_registered(monkeypatch) -> None:
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

    assert "get_design_brief_scope_matrix" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-scope-matrices://{brief_id}"]
        == "design_brief_scope_matrix_detail"
    )
