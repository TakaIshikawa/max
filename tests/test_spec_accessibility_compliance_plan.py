"""Tests for TactSpec accessibility compliance plan generation."""

from __future__ import annotations

import json

from max.spec import generate_accessibility_compliance_plan as exported_generate
from max.spec import render_accessibility_compliance_plan_markdown as exported_render
from max.spec.accessibility_compliance_plan import (
    ACCESSIBILITY_COMPLIANCE_PLAN_SCHEMA_VERSION,
    generate_accessibility_compliance_plan,
    render_accessibility_compliance_plan_markdown,
)
from max.spec.generator import generate_spec_preview


def test_generate_accessibility_compliance_plan_has_stable_shape(
    sample_unit, sample_evaluation
) -> None:
    sample_unit.tech_approach = "TypeScript browser dashboard and CLI with forms and CI output"
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)

    first = generate_accessibility_compliance_plan(sample_unit, sample_evaluation, tact_spec)
    second = generate_accessibility_compliance_plan(sample_unit, sample_evaluation, tact_spec)

    assert first == second
    assert first["schema_version"] == ACCESSIBILITY_COMPLIANCE_PLAN_SCHEMA_VERSION
    assert first["kind"] == "max.accessibility_compliance_plan"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["evaluation_available"] is True
    assert first["source"]["evidence_available"] is True
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["summary"]["accessibility_gate"] == "ready_with_checks"
    assert first["summary"]["target_user"] == "MCP server maintainer"
    assert first["summary"]["highest_severity"] == "critical"
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "summary",
        "audit_scope",
        "compliance_checks",
        "assistive_technology_tests",
        "remediation_backlog",
        "owner_roles",
        "launch_gate_checklist",
    }
    assert [check["id"] for check in first["compliance_checks"]][:4] == [
        "A11Y-C1",
        "A11Y-C2",
        "A11Y-C3",
        "A11Y-C4",
    ]
    assert any(
        check["wcag_reference"] == "WCAG 2.2 2.1.1 Keyboard"
        for check in first["compliance_checks"]
    )
    assert any(
        test["assistive_technology"] == "Screen reader with terminal"
        for test in first["assistive_technology_tests"]
    )
    assert first["remediation_backlog"][0]["priority"] == "P1"
    assert first["launch_gate_checklist"][-1]["id"] == "A11Y-G6"


def test_generate_accessibility_compliance_plan_degrades_without_evaluation(sample_unit) -> None:
    sample_unit.evidence_rationale = ""
    sample_unit.inspiring_insights = []
    sample_unit.evidence_signals = []

    plan = generate_accessibility_compliance_plan(sample_unit)

    assert plan["source"]["evaluation_available"] is False
    assert plan["source"]["evidence_available"] is False
    assert plan["summary"]["recommendation"] is None
    assert plan["summary"]["overall_score"] is None
    assert plan["summary"]["accessibility_gate"] == "blocked"
    assert any(check["id"] == "A11Y-C8" for check in plan["compliance_checks"])
    assert any(item["id"] == "A11Y-R5" for item in plan["remediation_backlog"])
    assert plan["launch_gate_checklist"][-1]["evidence_required_before_launch"] is False

    markdown = render_accessibility_compliance_plan_markdown(plan)
    assert "- Evaluation available: false" in markdown
    assert "- Evidence available: false" in markdown
    assert "- Accessibility gate: blocked" in markdown


def test_render_accessibility_compliance_plan_markdown_is_deterministic(
    sample_unit, sample_evaluation
) -> None:
    plan = generate_accessibility_compliance_plan(sample_unit, sample_evaluation)

    first = render_accessibility_compliance_plan_markdown(plan)
    second = render_accessibility_compliance_plan_markdown(plan)

    assert first == second
    assert first.startswith("# MCP Test Framework Accessibility Compliance Plan")
    assert f"- Schema version: {ACCESSIBILITY_COMPLIANCE_PLAN_SCHEMA_VERSION}" in first
    assert "## Audit Scope" in first
    assert "## WCAG-Oriented Checks" in first
    assert "## Assistive Technology Tests" in first
    assert "## Remediation Backlog" in first
    assert "## Owner Roles" in first
    assert "## Launch Gate Checklist" in first
    assert "### A11Y-C4: WCAG 2.2 2.1.1 Keyboard" in first
    assert "### AT-1: Keyboard-only workflow" in first


def test_accessibility_compliance_plan_is_json_serializable_and_exported(
    sample_unit, sample_evaluation
) -> None:
    plan = exported_generate(sample_unit, sample_evaluation)
    markdown = exported_render(plan)

    assert json.loads(json.dumps(plan))["idea_id"] == "bu-test001"
    assert markdown.startswith("# MCP Test Framework Accessibility Compliance Plan")
