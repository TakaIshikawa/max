from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_qa_test_plan import KIND, SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_qa_test_plan_detail,
    get_design_brief_qa_test_plan,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_qa_test_plan_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_qa_test_plan.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_qa_test_plan_brief_id(mcp_qa_test_plan_db) -> str:
    store = Store(db_path=mcp_qa_test_plan_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-qa-lead",
            title="QA Test Plan MCP Lead",
            one_liner="Expose QA test plans for design brief implementation handoff.",
            category="application",
            problem="Agents cannot validate generated implementation work from MCP.",
            solution="Return deterministic test suites, coverage, and evidence gaps.",
            value_proposition="Make build handoff quality auditable.",
            specific_user="implementation agent",
            buyer="engineering lead",
            workflow_context="autonomous implementation review",
            why_now="MCP consumers need QA artifacts alongside design briefs.",
            validation_plan="Run MCP JSON and Markdown responses against seeded briefs.",
            domain_risks=["Generated changes can miss acceptance coverage."],
            evidence_signals=["sig-mcp-qa-1"],
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-mcp-qa-support",
            title="QA Test Plan MCP Support",
            one_liner="Trace MCP QA plans to acceptance criteria and gaps.",
            category="application",
            problem="Handoff artifacts omit sparse-data and regression scenarios.",
            solution="Expose acceptance, regression, automation, and gap checks.",
            value_proposition="Reduce untested autonomous build output.",
            specific_user="QA engineer",
            buyer="product owner",
            workflow_context="release validation workflow",
            validation_plan="Compare structured QA plans with readable Markdown.",
            domain_risks=["Missing evidence can hide launch blockers."],
            evidence_signals=["sig-mcp-qa-2"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(support)

        return store.insert_design_brief(
            ProjectBrief(
                title="QA Test Plan MCP Brief",
                domain="developer-tools",
                theme="mcp-qa-plan",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=support)],
                readiness_score=84.0,
                why_this_now="Autonomous MCP consumers need executable QA guidance.",
                merged_product_concept=(
                    "A design brief QA test plan exposed through MCP JSON and Markdown."
                ),
                synthesis_rationale="Combines implementation scenarios, acceptance coverage, and gap tracking.",
                mvp_scope=[
                    "MCP JSON QA test plan tool",
                    "MCP Markdown QA test plan export",
                ],
                first_milestones=["Expose QA test plans over MCP"],
                validation_plan="Verify test scenarios, acceptance coverage, and gaps in MCP responses.",
                risks=[
                    "Generated changes can miss acceptance coverage.",
                    "Missing evidence can hide launch blockers.",
                ],
                source_idea_ids=[lead.id, support.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_qa_test_plan_json(seeded_qa_test_plan_brief_id) -> None:
    result = get_design_brief_qa_test_plan(seeded_qa_test_plan_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert result["source"]["entity_type"] == "design_brief"
    assert result["source"]["id"] == seeded_qa_test_plan_brief_id
    assert result["design_brief"]["id"] == seeded_qa_test_plan_brief_id
    assert result["design_brief"]["title"] == "QA Test Plan MCP Brief"
    assert [suite["coverage_type"] for suite in result["test_suites"]] == [
        "unit",
        "integration",
        "acceptance",
        "regression",
    ]
    acceptance_suite = next(
        suite for suite in result["test_suites"] if suite["coverage_type"] == "acceptance"
    )
    assert acceptance_suite["test_cases"]
    assert "acceptance" in acceptance_suite["name"].lower()
    assert result["critical_paths"]
    assert result["automation_candidates"]
    assert result["manual_review_checks"]
    assert "evidence_gaps" in result
    assert result["summary"]["evidence_gap_count"] == len(result["evidence_gaps"])


def test_get_design_brief_qa_test_plan_markdown(
    seeded_qa_test_plan_brief_id,
) -> None:
    result = get_design_brief_qa_test_plan(
        seeded_qa_test_plan_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_qa_test_plan_brief_id
    assert result["format"] == "markdown"
    markdown = result["markdown"]
    assert markdown.startswith("# QA Test Plan: QA Test Plan MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{seeded_qa_test_plan_brief_id}`" in markdown
    assert "## Test Suites" in markdown
    assert "Acceptance coverage for build handoff readiness" in markdown
    assert "## Critical Paths" in markdown
    assert "## Evidence Gaps" in markdown


def test_get_design_brief_qa_test_plan_not_found(mcp_qa_test_plan_db) -> None:
    result = get_design_brief_qa_test_plan("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_qa_test_plan_invalid_format(
    seeded_qa_test_plan_brief_id,
) -> None:
    result = get_design_brief_qa_test_plan(
        seeded_qa_test_plan_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported QA test plan format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_qa_test_plan_resource(seeded_qa_test_plan_brief_id) -> None:
    result = json.loads(design_brief_qa_test_plan_detail(seeded_qa_test_plan_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_qa_test_plan_brief_id
    assert result["test_suites"]


def test_create_mcp_server_registers_qa_test_plan_tool(monkeypatch) -> None:
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

    assert "get_design_brief_qa_test_plan" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-qa-test-plans://{brief_id}"]
        == "design_brief_qa_test_plan_detail"
    )
