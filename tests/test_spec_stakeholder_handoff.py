"""Tests for stakeholder handoff generation."""

from __future__ import annotations

import json

from max.spec.generator import generate_spec_preview
from max.spec.stakeholder_handoff import (
    STAKEHOLDER_HANDOFF_SCHEMA_VERSION,
    generate_stakeholder_handoff,
    render_stakeholder_handoff_markdown,
)


def test_generate_stakeholder_handoff_maps_unit_and_spec(sample_unit, sample_evaluation):
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)

    handoff = generate_stakeholder_handoff(sample_unit, sample_evaluation, tact_spec)

    assert handoff["schema_version"] == STAKEHOLDER_HANDOFF_SCHEMA_VERSION
    assert handoff["kind"] == "max.stakeholder_handoff"
    assert handoff["idea_id"] == "bu-test001"
    assert handoff["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert handoff["summary"]["title"] == "MCP Test Framework"
    assert handoff["summary"]["target_user"] == "MCP server maintainer"
    assert handoff["summary"]["buyer"] == "developer platform lead"
    assert handoff["summary"]["recommendation"] == "yes"
    assert handoff["summary"]["overall_score"] == 78.0
    assert {role["role"] for role in handoff["owner_roles"]} >= {
        "product_owner",
        "technical_owner",
        "validation_owner",
        "launch_owner",
        "risk_owner",
    }
    assert [checkpoint["id"] for checkpoint in handoff["decision_checkpoints"]][:4] == [
        "DC1",
        "DC2",
        "DC3",
        "DC4",
    ]
    assert handoff["evidence_references"] == [
        {
            "id": "EV1",
            "type": "insight",
            "reference_id": "ins-test001",
            "description": "Problem, timing, or opportunity evidence used to create the idea.",
        },
        {
            "id": "EV2",
            "type": "signal",
            "reference_id": "sig-test001",
            "description": "Source signal supporting the idea or validation path.",
        },
    ]
    assert handoff["unresolved_risks"][0]["description"] == "protocol churn"
    assert any(risk["description"] == "Niche audience" for risk in handoff["unresolved_risks"])
    assert json.loads(json.dumps(handoff))["idea_id"] == "bu-test001"


def test_generate_stakeholder_handoff_degrades_without_evaluation_or_spec(sample_unit):
    handoff = generate_stakeholder_handoff(sample_unit)

    assert handoff["source"]["evaluation_available"] is False
    assert handoff["source"]["tact_spec_schema_version"] is None
    assert handoff["summary"]["validation_plan"] == "run against five open-source MCP servers"
    assert [checkpoint["id"] for checkpoint in handoff["decision_checkpoints"]][:2] == [
        "DC0",
        "DC1",
    ]
    assert "missing_evaluation" in {
        risk["category"] for risk in handoff["unresolved_risks"]
    }


def test_render_stakeholder_handoff_markdown_includes_handoff_sections(
    sample_unit, sample_evaluation
):
    handoff = generate_stakeholder_handoff(
        sample_unit,
        sample_evaluation,
        generate_spec_preview(sample_unit, sample_evaluation),
    )

    markdown = render_stakeholder_handoff_markdown(handoff)

    assert markdown.startswith("# MCP Test Framework Stakeholder Handoff")
    assert "- Schema version: max-stakeholder-handoff/v1" in markdown
    assert "- Idea ID: bu-test001" in markdown
    assert "## Owner Roles" in markdown
    assert "### OR1: product_owner" in markdown
    assert "## Decision Checkpoints" in markdown
    assert "### DC1: Scope confirmation" in markdown
    assert "## Evidence References" in markdown
    assert "EV1 [insight]: ins-test001" in markdown
    assert "## Launch-Readiness Questions" in markdown
    assert "## Open Risks" in markdown
    assert "protocol churn" in markdown
