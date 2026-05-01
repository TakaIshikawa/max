from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_event_dictionary import KIND, SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_event_dictionary_detail,
    get_design_brief_event_dictionary,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_event_dictionary_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_event_dictionary.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_event_dictionary_brief_id(mcp_event_dictionary_db) -> str:
    store = Store(db_path=mcp_event_dictionary_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-event-dictionary-lead",
            title="Event Dictionary MCP Lead",
            one_liner="Expose design brief analytics event dictionaries over MCP.",
            category="application",
            problem="Agents cannot inspect analytics contracts during implementation planning.",
            solution="Return event groups, event definitions, metrics, and property contracts.",
            value_proposition="Make success metric instrumentation consistent across builds.",
            specific_user="platform engineer",
            buyer="VP of Engineering",
            workflow_context="release governance review",
            why_now="MCP consumers need analytics contracts alongside design briefs.",
            validation_plan="Review event contracts with platform engineers before implementation.",
            domain_risks=["Security approval may block rollout."],
            evidence_signals=["sig-mcp-event-dictionary-1"],
            domain="developer-tools",
            status="approved",
        )
        support = BuildableUnit(
            id="bu-mcp-event-dictionary-support",
            title="Event Dictionary MCP Support",
            one_liner="Trace event contracts back to source ideas and evidence ids.",
            category="application",
            problem="Analytics handoffs lose source traceability.",
            solution="Attach source idea ids and evidence references to generated events.",
            value_proposition="Reduce analytics implementation ambiguity.",
            specific_user="analytics engineer",
            buyer="product owner",
            workflow_context="instrumentation planning",
            validation_plan="Compare MCP JSON and Markdown event dictionary responses.",
            domain_risks=["Evidence notes may contain sensitive content."],
            evidence_signals=["sig-mcp-event-dictionary-2"],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(support)

        return store.insert_design_brief(
            ProjectBrief(
                title="Event Dictionary MCP Brief",
                domain="developer-tools",
                theme="event-dictionary-mcp-export",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=support)],
                readiness_score=88.0,
                why_this_now="MCP access lets agent clients consume event dictionaries.",
                merged_product_concept=(
                    "A release governance analytics dictionary for persisted design briefs."
                ),
                synthesis_rationale="The event dictionary module creates a stable artifact.",
                mvp_scope=["JSON event dictionary export", "Markdown event dictionary export"],
                first_milestones=["Return event dictionaries from MCP"],
                validation_plan="Confirm MCP payloads match the event dictionary renderer.",
                risks=[
                    "Security approval may block rollout.",
                    "Evidence notes may contain sensitive content.",
                ],
                source_idea_ids=[lead.id, support.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_event_dictionary_json(
    seeded_event_dictionary_brief_id,
) -> None:
    result = get_design_brief_event_dictionary(seeded_event_dictionary_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["kind"] == KIND
    assert result["source"]["entity_type"] == "design_brief"
    assert result["source"]["id"] == seeded_event_dictionary_brief_id
    assert result["design_brief"]["id"] == seeded_event_dictionary_brief_id
    assert result["design_brief"]["title"] == "Event Dictionary MCP Brief"
    assert result["summary"]["event_group_count"] == 5
    assert result["event_groups"]
    assert result["events"]
    assert result["property_contracts"]
    assert result["linked_metrics"]
    assert result["source_ideas"]

    activation = next(
        group for group in result["event_groups"] if group["category"] == "activation"
    )
    assert {event["event_name"] for event in activation["events"]} >= {
        "design_brief_workflow_started",
        "design_brief_first_value_reached",
    }
    first_event = next(
        event
        for event in result["events"]
        if event["event_name"] == "design_brief_workflow_started"
    )
    assert first_event["properties"] == [
        "brief_id",
        "account_id",
        "user_id",
        "workflow_context",
        "entry_point",
        "occurred_at",
    ]
    assert first_event["source_idea_ids"] == [
        "bu-mcp-event-dictionary-lead",
        "bu-mcp-event-dictionary-support",
    ]
    assert {contract["name"] for contract in result["property_contracts"]} >= {
        "brief_id",
        "account_id",
        "workflow_context",
        "occurred_at",
    }
    assert [idea["id"] for idea in result["source_ideas"]] == [
        "bu-mcp-event-dictionary-lead",
        "bu-mcp-event-dictionary-support",
    ]


def test_get_design_brief_event_dictionary_markdown(
    seeded_event_dictionary_brief_id,
) -> None:
    result = get_design_brief_event_dictionary(
        seeded_event_dictionary_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_event_dictionary_brief_id
    assert result["format"] == "markdown"
    markdown = result["markdown"]
    assert markdown.startswith("# Analytics Event Dictionary: Event Dictionary MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in markdown
    assert f"Design brief: `{seeded_event_dictionary_brief_id}`" in markdown
    assert "## Linked Metrics" in markdown
    assert "## Activation Events" in markdown
    assert "`design_brief_workflow_started`" in markdown
    assert "## Property Contracts" in markdown
    assert "### `workflow_context`" in markdown


def test_get_design_brief_event_dictionary_not_found(mcp_event_dictionary_db) -> None:
    result = get_design_brief_event_dictionary("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_event_dictionary_invalid_format(
    seeded_event_dictionary_brief_id,
) -> None:
    result = get_design_brief_event_dictionary(
        seeded_event_dictionary_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported event dictionary format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_event_dictionary_resource(
    seeded_event_dictionary_brief_id,
) -> None:
    result = json.loads(
        design_brief_event_dictionary_detail(seeded_event_dictionary_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_event_dictionary_brief_id
    assert result["event_groups"]
    assert result["property_contracts"]


def test_create_mcp_server_registers_event_dictionary_tool(monkeypatch) -> None:
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

    assert "get_design_brief_event_dictionary" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-event-dictionaries://{brief_id}"]
        == "design_brief_event_dictionary_detail"
    )
