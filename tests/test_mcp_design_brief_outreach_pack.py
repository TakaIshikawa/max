from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_outreach_pack import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_outreach_pack_detail,
    get_design_brief_outreach_pack,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_outreach_pack_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_outreach_pack.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_outreach_pack_brief_id(mcp_outreach_pack_db) -> str:
    store = Store(db_path=mcp_outreach_pack_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-outreach-lead",
            title="Outreach Pack Lead",
            one_liner="Recruit validation pilots from persisted design briefs.",
            category="application",
            problem="Validated ideas need concrete recruiting actions.",
            solution="Generate deterministic outreach packs.",
            value_proposition="Turn design briefs into pilot recruiting motion.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="pilot intake workflow",
            current_workaround="manual spreadsheet tracking",
            why_now="Validated specs need customer discovery.",
            validation_plan="Interview five workflow owners and recruit two pilots.",
            first_10_customers="developer platform teams",
            domain_risks=["Security review can delay pilots."],
            tech_approach="Python export module and CLI command.",
            suggested_stack={"language": "python"},
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-outreach-support",
            title="Outreach Pack Support",
            one_liner="Track sponsor questions for pilot recruiting.",
            category="application",
            problem="Pilot discovery loses sponsor context.",
            solution="Persist qualification and follow-up artifacts.",
            value_proposition="Make pilot readiness auditable.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="customer discovery handoff",
            domain_risks=["Recruiting messages may target the wrong owner."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)

        return store.insert_design_brief(
            ProjectBrief(
                title="Outreach Pack Brief",
                domain="developer-tools",
                theme="pilot-recruiting",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=88.0,
                why_this_now="Validation plans need pilot recruiting.",
                merged_product_concept="An outreach pack export for persisted design briefs.",
                synthesis_rationale="Completes customer discovery handoff.",
                mvp_scope=["JSON outreach pack", "Markdown outreach pack"],
                first_milestones=["Recruit first pilot"],
                validation_plan="Run discovery calls with five teams.",
                risks=["Security review can delay pilots."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_outreach_pack_json(seeded_outreach_pack_brief_id) -> None:
    result = get_design_brief_outreach_pack(seeded_outreach_pack_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == "max.design_brief.outreach_pack"
    assert result["design_brief"]["id"] == seeded_outreach_pack_brief_id
    assert result["design_brief"]["title"] == "Outreach Pack Brief"
    assert result["summary"]["buyer"] == "engineering manager"
    assert result["summary"]["specific_user"] == "platform engineer"
    assert [segment["id"] for segment in result["target_segments"]] == [
        "primary_workflow_owner",
        "economic_sponsors",
        "adjacent_evaluators",
    ]
    assert [template["id"] for template in result["templates"]] == [
        "email_primary_user",
        "dm_sponsor",
        "warm_intro",
    ]
    assert result["qualification_questions"]
    assert result["follow_up_artifacts"]


def test_get_design_brief_outreach_pack_markdown(
    seeded_outreach_pack_brief_id,
) -> None:
    result = get_design_brief_outreach_pack(
        seeded_outreach_pack_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_outreach_pack_brief_id
    assert result["format"] == "markdown"
    assert "# Outreach Pack: Outreach Pack Brief" in result["markdown"]
    assert "Schema: `max.design_brief.outreach_pack.v1`" in result["markdown"]
    assert "## Target Segments" in result["markdown"]


def test_get_design_brief_outreach_pack_not_found(mcp_outreach_pack_db) -> None:
    result = get_design_brief_outreach_pack("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_outreach_pack_invalid_format(
    seeded_outreach_pack_brief_id,
) -> None:
    result = get_design_brief_outreach_pack(
        seeded_outreach_pack_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported outreach pack format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"


def test_design_brief_outreach_pack_resource(seeded_outreach_pack_brief_id) -> None:
    result = json.loads(design_brief_outreach_pack_detail(seeded_outreach_pack_brief_id))

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_outreach_pack_brief_id
    assert result["target_segments"]


def test_create_mcp_server_registers_outreach_pack_tool(monkeypatch) -> None:
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

    assert "get_design_brief_outreach_pack" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-outreach-packs://{brief_id}"]
        == "design_brief_outreach_pack_detail"
    )
