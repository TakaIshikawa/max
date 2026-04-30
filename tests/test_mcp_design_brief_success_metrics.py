from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_success_metrics import SCHEMA_VERSION
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.server.mcp_tools import (
    create_mcp_server,
    design_brief_success_metrics_detail,
    get_design_brief_success_metrics,
    set_store_factory,
)
from max.store.db import Store
from max.types.buildable_unit import BuildableUnit


@pytest.fixture
def mcp_success_metrics_db(tmp_path):
    db_path = str(tmp_path / "mcp_design_brief_success_metrics.db")
    store = Store(db_path=db_path, wal_mode=True)
    store.close()

    set_store_factory(lambda: Store(db_path=db_path, wal_mode=True))
    yield db_path
    set_store_factory(lambda: Store(wal_mode=True))


@pytest.fixture
def seeded_success_metrics_brief_id(mcp_success_metrics_db) -> str:
    store = Store(db_path=mcp_success_metrics_db, wal_mode=True)
    try:
        lead = BuildableUnit(
            id="bu-mcp-success-metrics-lead",
            title="Success Metrics MCP Lead",
            one_liner="Expose design brief success metrics over MCP.",
            category="application",
            problem="Agents cannot inspect validation-ready success metrics.",
            solution="Return structured success metrics and Markdown exports.",
            value_proposition="Make success criteria available to autonomous planning.",
            specific_user="platform engineer",
            buyer="engineering manager",
            workflow_context="design brief execution planning",
            why_now="Design brief artifacts already support downstream workflows.",
            validation_plan="Review generated metrics with product and engineering leads.",
            domain_risks=["Security review can delay validation."],
            domain="developer-tools",
            status="approved",
        )
        supporting = BuildableUnit(
            id="bu-mcp-success-metrics-support",
            title="Success Metrics MCP Support",
            one_liner="Track guardrails and instrumentation for success metrics.",
            category="application",
            problem="Validation plans lose measurable follow-through.",
            solution="Persist metrics, guardrails, and events.",
            value_proposition="Make pilot measurement auditable.",
            specific_user="product operator",
            buyer="product lead",
            workflow_context="pilot measurement review",
            domain_risks=["Metric definitions can drift without a stable artifact."],
            domain="developer-tools",
            status="approved",
        )
        store.insert_buildable_unit(lead)
        store.insert_buildable_unit(supporting)

        return store.insert_design_brief(
            ProjectBrief(
                title="Success Metrics MCP Brief",
                domain="developer-tools",
                theme="mcp-export",
                lead=Candidate(unit=lead),
                supporting=[Candidate(unit=supporting)],
                readiness_score=88.0,
                why_this_now="MCP access lets agents consume success metrics.",
                merged_product_concept=(
                    "Expose deterministic design brief success metrics over JSON and Markdown."
                ),
                synthesis_rationale="The success metrics module creates a stable execution artifact.",
                mvp_scope=[
                    "JSON success metrics MCP tool",
                    "Markdown success metrics MCP tool",
                ],
                first_milestones=["Return structured success metrics from MCP"],
                validation_plan="Confirm the MCP payload matches the success metrics renderer.",
                risks=["Security review can delay validation."],
                source_idea_ids=[lead.id, supporting.id],
                design_status="approved",
            )
        )
    finally:
        store.close()


def test_get_design_brief_success_metrics_json(
    seeded_success_metrics_brief_id,
) -> None:
    result = get_design_brief_success_metrics(seeded_success_metrics_brief_id)

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["brief_id"] == seeded_success_metrics_brief_id
    assert result["title"] == "Success Metrics MCP Brief"
    assert result["north_star_metric"]["metric"] == "Qualified workflow success"
    assert result["north_star_metric"]["confidence"] == "high"
    assert [metric["id"] for metric in result["activation_metrics"]] == ["A1", "A2", "A3"]
    assert [metric["id"] for metric in result["retention_metrics"]] == ["R1", "R2"]
    assert [metric["id"] for metric in result["validation_metrics"]] == ["V1", "V2", "V3"]
    assert result["risk_guardrails"][0]["id"] == "G1"
    assert any(guardrail["severity"] == "high" for guardrail in result["risk_guardrails"])
    assert {event["event"] for event in result["instrumentation_events"]} >= {
        "success_metrics_report_generated",
        "activation_started",
        "first_value_reached",
        "workflow_repeated",
        "guardrail_triggered",
    }
    evidence_metric = result["validation_metrics"][1]
    assert "2 linked evidence item(s) across 2 source idea(s)" in evidence_metric["definition"]
    assert result["missing_inputs"] == []


def test_get_design_brief_success_metrics_markdown(
    seeded_success_metrics_brief_id,
) -> None:
    result = get_design_brief_success_metrics(
        seeded_success_metrics_brief_id,
        format="markdown",
    )

    assert result["id"] == seeded_success_metrics_brief_id
    assert result["format"] == "markdown"
    assert result["markdown"].startswith("# Success Metrics: Success Metrics MCP Brief")
    assert f"Schema: `{SCHEMA_VERSION}`" in result["markdown"]
    assert "## North Star Metric" in result["markdown"]
    assert "## Risk Guardrails" in result["markdown"]
    assert "## Instrumentation Events" in result["markdown"]


def test_get_design_brief_success_metrics_not_found(mcp_success_metrics_db) -> None:
    result = get_design_brief_success_metrics("dbf-missing")

    assert result["error"] == "Design brief not found: dbf-missing"
    assert result["code"] == 404
    assert result["details"]["resource_type"] == "design_brief"
    assert result["details"]["resource_id"] == "dbf-missing"


def test_get_design_brief_success_metrics_invalid_format(
    seeded_success_metrics_brief_id,
) -> None:
    result = get_design_brief_success_metrics(
        seeded_success_metrics_brief_id,
        format="yaml",
    )

    assert result["error"] == "Unsupported success metrics format: yaml"
    assert result["code"] == 400
    assert result["details"]["field"] == "format"
    assert result["details"]["expected"] == "json or markdown"
    assert result["details"]["actual"] == "yaml"


def test_design_brief_success_metrics_resource(
    seeded_success_metrics_brief_id,
) -> None:
    result = json.loads(
        design_brief_success_metrics_detail(seeded_success_metrics_brief_id)
    )

    assert result["schema_version"] == SCHEMA_VERSION
    assert result["brief_id"] == seeded_success_metrics_brief_id
    assert result["north_star_metric"]["metric"] == "Qualified workflow success"
    assert result["instrumentation_events"]


def test_create_mcp_server_registers_success_metrics_tool(monkeypatch) -> None:
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

    assert "get_design_brief_success_metrics" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["design-brief-success-metrics://{brief_id}"]
        == "design_brief_success_metrics_detail"
    )
