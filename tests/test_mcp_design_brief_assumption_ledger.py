from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_assumption_ledger import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_assumption_ledger_detail,
    get_design_brief_assumption_ledger,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_assumption_ledger_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_assumption_ledger.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_assumption_ledger_brief_id(mcp_assumption_ledger_db) -> str:
    store = Store(db_path=mcp_assumption_ledger_db, wal_mode=True)
    try:
        return _seed_design_brief(store)
    finally:
        store.close()


def test_get_design_brief_assumption_ledger_json(
    seeded_assumption_ledger_brief_id,
) -> None:
    first = get_design_brief_assumption_ledger(seeded_assumption_ledger_brief_id)
    second = get_design_brief_assumption_ledger(seeded_assumption_ledger_brief_id)

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.assumption_ledger"
    assert first["design_brief"]["id"] == seeded_assumption_ledger_brief_id
    assert first["design_brief"]["title"] == "Assumption Ledger MCP Brief"
    assert first["summary"]["assumption_count"] >= 8
    assert [group["id"] for group in first["assumption_groups"]] == [
        "desirability",
        "feasibility",
        "viability",
        "go_to_market",
    ]
    first_assumption = first["assumption_groups"][0]["assumptions"][0]
    assert first_assumption["id"] == "dba-desirability-01"
    assert first_assumption["statement"]
    assert first_assumption["evidence_links"]
    assert first["next_validation_actions"]


def test_get_design_brief_assumption_ledger_markdown(
    seeded_assumption_ledger_brief_id,
) -> None:
    result = get_design_brief_assumption_ledger(
        seeded_assumption_ledger_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_assumption_ledger_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith(
        "# Assumption Ledger: Assumption Ledger MCP Brief"
    )
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "### Desirability" in result["markdown"]
    assert "### Feasibility" in result["markdown"]
    assert "- **platform engineer has a recurring problem" in result["markdown"]
    assert "Confidence: `" in result["markdown"]
    assert "Validation action:" in result["markdown"]
    assert "## Next Validation Actions" in result["markdown"]


def test_get_design_brief_assumption_ledger_not_found(
    mcp_assumption_ledger_db,
) -> None:
    result = get_design_brief_assumption_ledger("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_assumption_ledger_invalid_format(
    seeded_assumption_ledger_brief_id,
) -> None:
    result = get_design_brief_assumption_ledger(
        seeded_assumption_ledger_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported assumption ledger format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_assumption_ledger_resource(
    seeded_assumption_ledger_brief_id,
) -> None:
    result = json.loads(
        design_brief_assumption_ledger_detail(seeded_assumption_ledger_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_assumption_ledger_brief_id
    assert result["assumption_groups"]
    assert result["next_validation_actions"]


def test_create_mcp_server_registers_assumption_ledger_tool(monkeypatch) -> None:
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

    assert "get_design_brief_assumption_ledger" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-assumption-ledger://{brief_id}"]
        == "design_brief_assumption_ledger_detail"
    )


def _seed_design_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-assumption-ledger-mcp",
        title="Assumption Ledger MCP Lead",
        one_liner="Expose design brief assumption ledgers over MCP",
        category="application",
        problem="Agents cannot inspect unresolved design brief assumptions.",
        solution="Return structured assumption ledgers and Markdown exports.",
        value_proposition="Make assumption risk visible to autonomous agents.",
        specific_user="platform engineer",
        buyer="VP of Engineering",
        workflow_context="agent release governance review",
        current_workaround="manual release notes and ad hoc approval chats",
        why_now="Agent releases are moving from experiments into production.",
        validation_plan="Interview platform engineers and engineering buyers before implementation.",
        first_10_customers="platform teams shipping production agents",
        domain_risks=["Security approval may block rollout."],
        evidence_rationale="Signals show release governance and validation gaps.",
        evidence_signals=["sig-release-governance", "sig-user-pain"],
        inspiring_insights=["ins-assumption-ledger"],
        tech_approach="Deterministic Python report over persisted design brief records.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Assumption Ledger MCP Brief",
            domain="developer-tools",
            theme="assumption-ledger-mcp-export",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0,
            why_this_now="MCP access lets agents consume the assumption ledger.",
            merged_product_concept=(
                "A release governance brief that names assumptions before build."
            ),
            synthesis_rationale="The ledger module already creates a stable artifact.",
            mvp_scope=["JSON assumption ledger", "Markdown assumption ledger"],
            first_milestones=["Return structured assumption ledgers over MCP"],
            validation_plan="Confirm the MCP payload matches the ledger renderer.",
            risks=["Security approval may block rollout."],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
