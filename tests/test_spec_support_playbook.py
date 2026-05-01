"""Tests for TactSpec support playbook generation."""

from __future__ import annotations

import json

from max.spec import generate_support_playbook as exported_generate
from max.spec import render_support_playbook_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.support_playbook import (
    SUPPORT_PLAYBOOK_SCHEMA_VERSION,
    generate_support_playbook,
    render_support_playbook_markdown,
)


def test_generate_support_playbook_has_stable_schema_shape(sample_unit, sample_evaluation) -> None:
    spec = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_support_playbook(sample_unit, sample_evaluation, spec)
    second = generate_support_playbook(sample_unit, sample_evaluation, spec)

    assert first == second
    assert first["schema_version"] == SUPPORT_PLAYBOOK_SCHEMA_VERSION
    assert first["kind"] == "max.support_playbook"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["idea_summary"] == {
        "title": "MCP Test Framework",
        "one_liner": "Standardized testing for MCP servers",
        "target_user": "MCP server maintainer",
        "buyer": "developer platform lead",
        "workflow_context": "pre-release CI validation",
        "primary_scope": "A CLI tool that validates MCP server implementations",
        "current_workaround": "manual protocol testing",
        "validation_plan": "run against five open-source MCP servers",
        "recommendation": "yes",
        "overall_score": 78.0,
        "support_goal": "Help MCP server maintainer complete pre-release CI validation.",
    }
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "idea_summary",
        "support_scenarios",
        "triage_questions",
        "escalation_paths",
        "known_limitations",
        "troubleshooting_checklist",
        "evidence_risk_notes",
    }
    assert [scenario["id"] for scenario in first["support_scenarios"]] == [
        "SC1",
        "SC2",
        "SC3",
        "SC4",
    ]
    assert [path["id"] for path in first["escalation_paths"]] == [
        "ESC1",
        "ESC2",
        "ESC3",
        "ESC4",
    ]
    assert any(item["id"] == "CHK6" for item in first["troubleshooting_checklist"])
    assert any(note["note"] == "protocol churn" for note in first["evidence_risk_notes"])
    assert any("signal:sig-test001" in note["evidence_links"] for note in first["evidence_risk_notes"])


def test_generate_support_playbook_is_json_serializable(sample_unit, sample_evaluation) -> None:
    playbook = generate_support_playbook(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(playbook))["idea_id"] == "bu-test001"


def test_render_support_playbook_markdown_is_deterministic(sample_unit, sample_evaluation) -> None:
    playbook = generate_support_playbook(sample_unit, sample_evaluation)

    first = render_support_playbook_markdown(playbook)
    second = render_support_playbook_markdown(playbook)

    assert first == second
    assert first.startswith("# MCP Test Framework Support Playbook")
    assert f"- Schema version: {SUPPORT_PLAYBOOK_SCHEMA_VERSION}" in first
    assert "## Likely Support Scenarios" in first
    assert "## Triage Questions" in first
    assert "## Escalation Paths" in first
    assert "## Known Limitations" in first
    assert "## Troubleshooting Checklist" in first
    assert "## Evidence-Linked Risk Notes" in first
    assert "### SC1: User cannot complete primary workflow" in first
    assert "### TQ5: Does it match a known risk?" in first
    assert "### ESC4: launch_owner (critical)" in first
    assert "protocol churn" in first
    assert "signal:sig-test001" in first


def test_generate_support_playbook_degrades_without_evaluation_or_spec(sample_unit) -> None:
    playbook = generate_support_playbook(sample_unit)

    assert playbook["source"]["evaluation_available"] is False
    assert playbook["source"]["tact_spec_available"] is False
    assert playbook["source"]["tact_spec_schema_version"] is None
    assert playbook["idea_summary"]["recommendation"] is None
    assert playbook["idea_summary"]["primary_scope"] == "A CLI tool that validates MCP server implementations"
    assert any(item["id"] == "LIM3" for item in playbook["known_limitations"])
    assert any(note["source"] == "missing_evaluation" for note in playbook["evidence_risk_notes"])
    assert any(path["id"] == "ESC4" for path in playbook["escalation_paths"])

    markdown = render_support_playbook_markdown(playbook)
    assert "- Evaluation available: false" in markdown
    assert "- Tact spec available: false" in markdown


def test_support_playbook_is_importable_from_spec_package(sample_unit, sample_evaluation) -> None:
    playbook = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(playbook)

    assert playbook["schema_version"] == SUPPORT_PLAYBOOK_SCHEMA_VERSION
    assert markdown.startswith("# MCP Test Framework Support Playbook")
