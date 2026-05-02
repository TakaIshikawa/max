from __future__ import annotations

import json

import max.spec.incident_response_plan as incident_response_plan
from max.server import mcp_tools
from max.server.mcp_tools import create_mcp_server, get_spec_incident_response_plan
from max.spec.generator import SPEC_PREVIEW_SCHEMA_VERSION
from max.spec.incident_response_plan import INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


class _FakeStore:
    def __init__(self, unit: BuildableUnit | None):
        self.unit = unit

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get_buildable_unit(self, idea_id: str):
        if self.unit and self.unit.id == idea_id:
            return self.unit
        return None

    def get_evaluation(self, idea_id: str):
        return None


def _unit() -> BuildableUnit:
    return BuildableUnit(
        id="bu-incident-mcp",
        title="Incident MCP",
        one_liner="Expose incident response guidance through MCP.",
        category=BuildableCategory.AUTOMATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="MCP clients cannot inspect incident handling guidance before autonomous rollout.",
        solution="Return the deterministic incident response plan through MCP.",
        target_users="agent consumers",
        specific_user="release agent",
        buyer="platform lead",
        workflow_context="GitHub deployment gate to Slack incident channel",
        value_proposition="Clients can prepare escalation and containment before launch.",
        validation_plan="Run a Slack and GitHub incident response exercise.",
        tech_approach=(
            "FastAPI service with GitHub checks, Slack escalation, OAuth, audit logs, "
            "Datadog dashboards, and secret rotation support."
        ),
        suggested_stack={
            "language": "python",
            "framework": "fastapi",
            "ci": "github-actions",
            "messaging": "Slack",
            "observability": "Datadog",
        },
        domain_risks=[
            "OAuth token leak could expose customer deployment metadata.",
            "GitHub API outage may delay rollback during SLO breaches.",
        ],
        evidence_rationale="Incident guidance needs to cite launch evidence.",
        inspiring_insights=["ins-incident-mcp"],
        evidence_signals=["sig-incident-mcp"],
        source_idea_ids=["src-incident-mcp"],
        domain="developer-tools",
        status="approved",
    )


def test_get_spec_incident_response_plan_returns_structured_plan(monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(_unit()))

    result = get_spec_incident_response_plan("bu-incident-mcp")

    assert json.loads(json.dumps(result)) == result
    assert result["schema_version"] == INCIDENT_RESPONSE_PLAN_SCHEMA_VERSION
    assert result["kind"] == "max.incident_response_plan"
    assert result["source"]["idea_id"] == "bu-incident-mcp"
    assert result["source"]["tact_spec_schema_version"] == SPEC_PREVIEW_SCHEMA_VERSION
    assert result["source"]["tact_spec_kind"] == "tact.project_spec"
    assert result["source"]["evidence_reference_count"] == 3
    assert result["summary"]["title"] == "Incident MCP"
    assert result["summary"]["security_risk_count"] >= 1
    assert result["summary"]["operational_risk_count"] >= 1
    assert set(result) >= {
        "summary",
        "incident_context",
        "severity_levels",
        "incident_classes",
        "escalation_roles",
        "triage_steps",
        "containment_actions",
        "communication_checkpoints",
        "postmortem_requirements",
        "evidence_references",
        "gaps",
    }
    assert set(result["evidence_references"]) == {
        "insight:ins-incident-mcp",
        "signal:sig-incident-mcp",
        "source_idea:src-incident-mcp",
    }
    assert {item["category"] for item in result["incident_classes"]} >= {
        "security_incident",
        "dependency_failure",
        "operational_degradation",
    }
    assert any(role["role"] == "incident_commander" for role in result["escalation_roles"])


def test_get_spec_incident_response_plan_missing_idea_returns_mcp_error(monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(None))

    result = get_spec_incident_response_plan("missing-incident-plan")

    assert result == {
        "error": "Idea not found: missing-incident-plan",
        "code": 404,
        "details": {
            "resource_type": "buildable_unit",
            "resource_id": "missing-incident-plan",
        },
    }


def test_get_spec_incident_response_plan_invalid_generator_result_returns_mcp_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(_unit()))
    monkeypatch.setattr(
        incident_response_plan,
        "generate_incident_response_plan",
        lambda tact_spec: {"source": {}, "summary": {}},
    )

    result = get_spec_incident_response_plan("bu-incident-mcp")

    assert result == {
        "error": "Invalid incident response plan result",
        "code": 400,
        "details": {"field": "severity_levels", "expected": "list"},
    }


def test_create_mcp_server_registers_spec_incident_response_plan_tool(monkeypatch) -> None:
    class FakeMCP:
        latest = None

        def __init__(self, name: str):
            self.name = name
            self.tools = []
            self.resources = {}
            FakeMCP.latest = self

        def tool(self, fn=None, *args, **kwargs):
            self.tools.append(fn.__name__)
            return fn

        def resource(self, uri):
            def decorator(fn):
                self.resources[uri] = fn.__name__
                return fn

            return decorator

    monkeypatch.setattr(mcp_tools, "FastMCP", FakeMCP)

    create_mcp_server()

    assert "get_spec_incident_response_plan" in FakeMCP.latest.tools
