from __future__ import annotations

import json

import max.spec.release_readiness_gate as release_readiness_gate
from max.server import mcp_tools
from max.server.mcp_tools import (
    create_mcp_server,
    get_spec_release_readiness_gate,
    spec_release_readiness_gate_detail,
)
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
        id="bu-release-gate-mcp",
        title="Release Gate MCP",
        one_liner="Expose release gate decisions through MCP.",
        category=BuildableCategory.AUTOMATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="MCP clients cannot inspect final TactSpec release readiness.",
        solution="Return the deterministic release readiness gate through MCP.",
        target_users="agent consumers",
        specific_user="release agent",
        buyer="platform lead",
        workflow_context="pre-publication TactSpec release review",
        value_proposition="Clients can block execution until release evidence is complete.",
        validation_plan="Call the tool with complete and incomplete generated gates.",
        tech_approach="Wrap the existing release readiness gate generator.",
        suggested_stack={"language": "python"},
        domain="developer-tools",
        status="approved",
    )


def _gate_payload() -> dict:
    return {
        "schema_version": "max-release-readiness-gate/v1",
        "kind": "max.release_readiness_gate",
        "source": {"idea_id": "bu-release-gate-mcp"},
        "summary": {
            "title": "Release Gate MCP",
            "decision": "no-go",
            "go": False,
            "ready_dimension_count": 5,
            "blocker_count": 1,
        },
        "readiness_dimensions": [
            {
                "id": "scope",
                "label": "Scope",
                "status": "ready",
                "missing_evidence": [],
                "remediation": "",
            },
            {
                "id": "security",
                "label": "Security",
                "status": "blocked",
                "missing_evidence": ["artifacts.security_review"],
                "remediation": "Complete security review.",
            },
        ],
        "blockers": [
            {
                "id": "BLK1",
                "dimension_id": "security",
                "severity": "critical",
                "description": "Complete security review.",
                "missing_evidence": ["artifacts.security_review"],
                "owner": "security_owner",
            }
        ],
        "required_signoffs": [
            {
                "id": "SO3",
                "role": "security_owner",
                "status": "blocked",
                "requirement": "Security review has no unresolved release blockers.",
                "blocked_by_dimensions": ["security"],
            }
        ],
    }


def test_get_spec_release_readiness_gate_returns_structured_payload(monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(_unit()))

    def fake_generate(tact_spec: dict) -> dict:
        assert tact_spec["source"]["idea_id"] == "bu-release-gate-mcp"
        return _gate_payload()

    monkeypatch.setattr(
        release_readiness_gate,
        "generate_release_readiness_gate",
        fake_generate,
    )

    result = get_spec_release_readiness_gate("bu-release-gate-mcp")

    assert result["kind"] == "max.release_readiness_gate"
    assert result["readiness_status"] == {
        "status": "blocked",
        "decision": "no-go",
        "go": False,
        "ready_dimension_count": 5,
        "blocker_count": 1,
    }
    assert result["blocking_checks"] == result["blockers"]
    assert result["warnings"] == []
    assert result["recommended_next_actions"][0] == {
        "type": "resolve_blocker",
        "dimension_id": "security",
        "title": "BLK1",
        "action": "Complete security review.",
    }
    assert result["recommended_next_actions"][1]["type"] == "complete_signoff"


def test_get_spec_release_readiness_gate_missing_idea_returns_mcp_error(monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(None))

    result = get_spec_release_readiness_gate("missing-release-gate")

    assert result == {
        "error": "Idea not found: missing-release-gate",
        "code": 404,
        "details": {
            "resource_type": "buildable_unit",
            "resource_id": "missing-release-gate",
        },
    }


def test_get_spec_release_readiness_gate_invalid_generator_result_returns_mcp_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(_unit()))
    monkeypatch.setattr(
        release_readiness_gate,
        "generate_release_readiness_gate",
        lambda tact_spec: {"summary": {}},
    )

    result = get_spec_release_readiness_gate("bu-release-gate-mcp")

    assert result == {
        "error": "Invalid release readiness gate result",
        "code": 400,
        "details": {"field": "blockers", "expected": "list"},
    }


def test_spec_release_readiness_gate_resource_returns_pretty_json(monkeypatch) -> None:
    monkeypatch.setattr(mcp_tools, "_store_factory", lambda: _FakeStore(_unit()))
    monkeypatch.setattr(
        release_readiness_gate,
        "generate_release_readiness_gate",
        lambda tact_spec: _gate_payload(),
    )

    rendered = spec_release_readiness_gate_detail("bu-release-gate-mcp")
    payload = json.loads(rendered)

    assert rendered.startswith("{\n  ")
    assert payload["source"]["idea_id"] == "bu-release-gate-mcp"
    assert payload["readiness_status"]["status"] == "blocked"


def test_create_mcp_server_registers_release_readiness_gate_tool_and_resource(
    monkeypatch,
) -> None:
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

    assert "get_spec_release_readiness_gate" in FakeMCP.latest.tools
    assert (
        FakeMCP.latest.resources["ideas://{idea_id}/spec-release-readiness-gate"]
        == "spec_release_readiness_gate_detail"
    )
