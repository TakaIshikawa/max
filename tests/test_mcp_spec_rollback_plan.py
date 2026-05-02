from __future__ import annotations

import max.spec as spec
from max.server import mcp_tools
from max.server.mcp_tools import create_mcp_server, get_spec_rollback_plan


def test_get_spec_rollback_plan_delegates_to_existing_generator(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def fake_generate(unit, evaluation, tact_spec):
        calls["unit"] = unit
        calls["evaluation"] = evaluation
        calls["tact_spec"] = tact_spec
        return {
            "schema_version": "max-rollback-plan/v1",
            "kind": "max.rollback_plan",
            "idea_id": "bu-rollback-mcp",
            "summary": {"title": "Rollback MCP", "rollback_window": "during rollout"},
            "rollback_triggers": [{"id": "trigger_validation_failure"}],
            "reversible_migration_steps": [
                {
                    "id": "step_1",
                    "action": "Restore previous executable version",
                    "owner": "technical_owner",
                }
            ],
            "data_backup_requirements": [],
            "monitoring_signals": [],
            "owner_roles": [],
            "go_no_go_checklist": [],
        }

    monkeypatch.setattr(spec, "generate_rollback_plan", fake_generate)

    result = get_spec_rollback_plan({"tact_spec": _complete_tact_spec()})

    assert result["kind"] == "max.rollback_plan"
    assert result["idea_id"] == "bu-rollback-mcp"
    assert result["rollback_steps"] == result["reversible_migration_steps"]
    assert result["rollback_steps"][0]["action"] == "Restore previous executable version"
    assert calls["evaluation"] is None
    assert calls["tact_spec"]["source"]["idea_id"] == "bu-rollback-mcp"
    assert calls["unit"].id == "bu-rollback-mcp"
    assert calls["unit"].title == "Rollback MCP"


def test_get_spec_rollback_plan_accepts_minimal_direct_tact_spec_payload() -> None:
    result = get_spec_rollback_plan(
        {
            "schema_version": "tact-spec-preview/v1",
            "kind": "tact.project_spec",
            "source": {"idea_id": "bu-minimal-rollback", "status": "approved"},
            "project": {"title": "Minimal Rollback", "summary": "Minimal rollback evidence."},
        }
    )

    assert result["kind"] == "max.rollback_plan"
    assert result["idea_id"] == "bu-minimal-rollback"
    assert result["summary"]["title"] == "Minimal Rollback"
    assert result["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert result["rollback_steps"]
    assert result["rollback_steps"] == result["reversible_migration_steps"]


def test_get_spec_rollback_plan_invalid_payload_returns_mcp_error() -> None:
    result = get_spec_rollback_plan({"tact_spec": []})

    assert result == {
        "error": "Invalid TactSpec payload",
        "code": 400,
        "details": {"field": "tact_spec", "expected": "non-empty object"},
    }


def test_create_mcp_server_registers_spec_rollback_plan_tool(monkeypatch) -> None:
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

    assert "get_spec_rollback_plan" in FakeMCP.latest.tools


def _complete_tact_spec() -> dict:
    return {
        "schema_version": "tact-spec-preview/v1",
        "kind": "tact.project_spec",
        "source": {
            "system": "max",
            "type": "idea",
            "idea_id": "bu-rollback-mcp",
            "status": "approved",
            "domain": "developer-tools",
            "category": "agent-safety",
        },
        "project": {
            "title": "Rollback MCP",
            "summary": "Expose rollback planning through MCP.",
            "value_proposition": "Give agents operational rollback guidance before launch.",
            "target_users": "engineering teams",
            "specific_user": "release agent",
            "buyer": "platform lead",
            "workflow_context": "pre-launch rollback approval",
        },
        "solution": {
            "approach": "Return the existing deterministic rollback plan artifact.",
            "technical_approach": "Adapt TactSpec fields and delegate to the rollback generator.",
            "suggested_stack": {"language": "python", "framework": "fastapi"},
        },
        "execution": {
            "validation_plan": "Run rollback plan generation against complete and minimal specs.",
            "first_10_customers": "three platform teams",
            "risks": ["Rollback evidence may be incomplete."],
        },
        "evidence": {
            "rationale": "MCP clients need rollback guidance.",
            "insight_ids": ["insight-1"],
            "signal_ids": ["signal-1"],
            "source_idea_ids": ["source-1"],
        },
    }
