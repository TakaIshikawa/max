from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_support_playbook import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_support_playbook_detail,
    get_design_brief_support_playbook,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_support_playbook_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_support_playbook.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_support_playbook_brief_id(mcp_support_playbook_db) -> str:
    store = Store(db_path=mcp_support_playbook_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-support-playbook",
            title="Support Playbook MCP Lead",
            one_liner="Expose support playbook handoffs over MCP.",
            category="application",
            problem="Agent consumers cannot inspect support playbooks.",
            solution="Return structured support playbooks and Markdown exports.",
            value_proposition="Make operational handoffs available to support automation.",
            specific_user="support engineer",
            buyer="support lead",
            workflow_context="pilot support intake",
            current_workaround="manual support notes",
            why_now="Support teams need deterministic handoff artifacts before rollout.",
            validation_plan="Review generated support playbooks with support owners.",
            domain_risks=["Security review can delay support access."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        return store.insert_design_brief(
            ProjectBrief(
                title="Support Playbook MCP Brief",
                domain="developer-tools",
                theme="support-playbook-mcp-export",
                lead=Candidate(unit=lead),
                supporting=[],
                readiness_score=84.0,
                why_this_now="MCP access lets agents consume support playbooks.",
                merged_product_concept="A support playbook export for persisted design briefs.",
                synthesis_rationale="Covers operational handoff after product planning.",
                mvp_scope=["Support playbook JSON", "Support playbook Markdown"],
                first_milestones=["Return support playbook JSON from MCP"],
                validation_plan="Confirm support owners can resolve pilot tickets.",
                risks=["Security review can delay support access."],
                source_idea_ids=[lead.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_support_playbook_json(
    seeded_support_playbook_brief_id,
) -> None:
    result = get_design_brief_support_playbook(seeded_support_playbook_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.support_playbook"
    assert result["design_brief"]["id"] == seeded_support_playbook_brief_id
    assert result["design_brief"]["title"] == "Support Playbook MCP Brief"
    assert result["summary"]["target_user"] == "support engineer"
    assert result["onboarding_checks"]
    assert result["support_scenarios"]
    assert result["monitoring_signals"]


def test_get_design_brief_support_playbook_markdown(
    seeded_support_playbook_brief_id,
) -> None:
    result = get_design_brief_support_playbook(
        seeded_support_playbook_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_support_playbook_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith(
        "# Support Playbook: Support Playbook MCP Brief"
    )
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Support Context" in result["markdown"]
    assert "## Troubleshooting Flows" in result["markdown"]


def test_get_design_brief_support_playbook_not_found(
    mcp_support_playbook_db,
) -> None:
    result = get_design_brief_support_playbook("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_support_playbook_invalid_format(
    seeded_support_playbook_brief_id,
) -> None:
    result = get_design_brief_support_playbook(
        seeded_support_playbook_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported support playbook format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_support_playbook_resource(
    seeded_support_playbook_brief_id,
) -> None:
    result = json.loads(
        design_brief_support_playbook_detail(seeded_support_playbook_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_support_playbook_brief_id
    assert result["support_scenarios"]
    assert result["monitoring_signals"]


def test_create_mcp_server_registers_support_playbook_tool(monkeypatch) -> None:
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

    assert "get_design_brief_support_playbook" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-briefs://{brief_id}/support-playbook"]
        == "design_brief_support_playbook_detail"
    )
