from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_instrumentation_plan import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_instrumentation_plan_detail,
    get_design_brief_instrumentation_plan,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_instrumentation_plan_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_instrumentation_plan.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_instrumentation_plan_brief_id(mcp_instrumentation_plan_db) -> str:
    store = Store(db_path=mcp_instrumentation_plan_db, wal_mode=True)
    try:
        return _seed_design_brief(store)
    finally:
        store.close()


def test_get_design_brief_instrumentation_plan_json(
    seeded_instrumentation_plan_brief_id,
) -> None:
    first = get_design_brief_instrumentation_plan(seeded_instrumentation_plan_brief_id)
    second = get_design_brief_instrumentation_plan(seeded_instrumentation_plan_brief_id)

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.design_brief.instrumentation_plan"
    assert first["design_brief"]["id"] == seeded_instrumentation_plan_brief_id
    assert first["design_brief"]["title"] == "Instrumentation Plan MCP Brief"
    assert first["summary"]["activation_event_count"] >= 1
    assert first["summary"]["value_event_count"] >= 1
    assert first["summary"]["retention_event_count"] >= 1
    assert first["summary"]["guardrail_event_count"] >= 1
    assert {event["name"] for event in first["events"]} >= {
        "activation_started",
        "first_value_reached",
        "core_workflow_repeated",
        "guardrail_alert_triggered",
    }


def test_get_design_brief_instrumentation_plan_markdown(
    seeded_instrumentation_plan_brief_id,
) -> None:
    result = get_design_brief_instrumentation_plan(
        seeded_instrumentation_plan_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_instrumentation_plan_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith(
        "# Instrumentation Plan: Instrumentation Plan MCP Brief"
    )
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## Events" in result["markdown"]
    assert "## Activation Funnel" in result["markdown"]
    assert "## Retention Checkpoints" in result["markdown"]
    assert "## Guardrail Alerts" in result["markdown"]


def test_get_design_brief_instrumentation_plan_not_found(
    mcp_instrumentation_plan_db,
) -> None:
    result = get_design_brief_instrumentation_plan("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_instrumentation_plan_invalid_format(
    seeded_instrumentation_plan_brief_id,
) -> None:
    result = get_design_brief_instrumentation_plan(
        seeded_instrumentation_plan_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported instrumentation plan format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_instrumentation_plan_resource(
    seeded_instrumentation_plan_brief_id,
) -> None:
    result = json.loads(
        design_brief_instrumentation_plan_detail(seeded_instrumentation_plan_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["design_brief"]["id"] == seeded_instrumentation_plan_brief_id
    assert result["events"]
    assert result["activation_funnel_steps"]


def test_create_mcp_server_registers_instrumentation_plan_tool(monkeypatch) -> None:
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

    assert "get_design_brief_instrumentation_plan" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-instrumentation-plan://{brief_id}"]
        == "design_brief_instrumentation_plan_detail"
    )


def _seed_design_brief(store: Store) -> str:
    lead = BuildableUnit(
        id="bu-instrumentation-plan-mcp",
        title="Instrumentation Plan MCP Lead",
        one_liner="Expose design brief instrumentation plans over MCP",
        category="application",
        problem="Agents cannot inspect instrumentation plans from MCP.",
        solution="Return structured instrumentation plans and Markdown exports.",
        value_proposition="Make validation analytics visible to autonomous agents.",
        specific_user="platform engineer",
        buyer="VP of Engineering",
        workflow_context="release governance review",
        why_now="Agent releases are moving from experiments into production.",
        validation_plan="Interview platform engineers before implementation.",
        domain_risks=[],
        domain="developer-tools",
        status="approved",
    )
    store.insert_buildable_unit(lead)
    return store.insert_design_brief(
        ProjectBrief(
            title="Instrumentation Plan MCP Brief",
            domain="developer-tools",
            theme="instrumentation-plan-mcp-export",
            lead=Candidate(unit=lead),
            supporting=[],
            readiness_score=86.0,
            why_this_now="MCP access lets agents consume instrumentation plans.",
            merged_product_concept=(
                "A release governance brief with implementation-ready analytics."
            ),
            synthesis_rationale="The instrumentation module already creates a stable artifact.",
            mvp_scope=["JSON instrumentation plan", "Markdown instrumentation plan"],
            first_milestones=["Return instrumentation plans from MCP"],
            validation_plan="Confirm MCP payloads match the instrumentation renderer.",
            risks=[
                "Security approval may block rollout.",
                "Analytics gaps may hide failed reviews.",
            ],
            source_idea_ids=[lead.id],
            design_status="approved",
        )
    )
