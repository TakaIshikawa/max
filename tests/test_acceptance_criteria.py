"""Tests for acceptance criteria generation."""

from __future__ import annotations

import json

from max.spec.acceptance_criteria import (
    ACCEPTANCE_CRITERIA_SCHEMA_VERSION,
    generate_acceptance_criteria,
    render_acceptance_criteria_markdown,
)


def test_generate_acceptance_criteria_is_deterministic(sample_unit, sample_evaluation):
    evidence_density = {
        "density_score": 72.5,
        "missing_evidence_warnings": [],
    }

    first = generate_acceptance_criteria(sample_unit, sample_evaluation, evidence_density)
    second = generate_acceptance_criteria(sample_unit, sample_evaluation, evidence_density)

    assert first == second
    assert first["schema_version"] == ACCEPTANCE_CRITERIA_SCHEMA_VERSION
    assert first["kind"] == "max.acceptance_criteria"
    assert first["idea_id"] == "bu-test001"
    assert first["summary"]["recommendation"] == "yes"
    assert [item["id"] for item in first["functional_criteria"]] == [
        "AC-F1",
        "AC-F2",
        "AC-F3",
        "AC-F4",
        "AC-F5",
        "AC-F6",
    ]
    assert [item["id"] for item in first["non_functional_criteria"]] == [
        "AC-NF1",
        "AC-NF2",
        "AC-NF3",
        "AC-NF4",
        "AC-NF5",
    ]
    assert any(item["id"] == "EC6" for item in first["edge_cases"])
    assert {"type": "insight", "id": "ins-test001", "uri": "insights://ins-test001"} in first["evidence_links"]
    assert {"type": "signal", "id": "sig-test001", "uri": "signals://sig-test001"} in first["evidence_links"]
    assert any("Niche audience" in item for item in first["out_of_scope"])


def test_generate_acceptance_criteria_handles_sparse_idea(sample_unit):
    sparse_unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "validation_plan": "",
            "inspiring_insights": [],
            "evidence_signals": [],
            "domain_risks": [],
            "composability_notes": "",
        }
    )

    criteria = generate_acceptance_criteria(sparse_unit)

    assert criteria["summary"]["recommendation"] is None
    assert len(criteria["evidence_links"]) == 0
    assert any(edge_case["id"] == "EC4" for edge_case in criteria["edge_cases"])
    assert json.loads(json.dumps(criteria))["kind"] == "max.acceptance_criteria"


def test_render_acceptance_criteria_markdown_is_stable_and_traceable(
    sample_unit,
    sample_evaluation,
):
    evidence_density = {
        "density_score": 72.5,
        "missing_evidence_warnings": [],
    }
    criteria = generate_acceptance_criteria(sample_unit, sample_evaluation, evidence_density)

    first = render_acceptance_criteria_markdown(criteria)
    second = render_acceptance_criteria_markdown(criteria)

    assert first == second
    assert first.endswith("\n")
    assert first.startswith("# Acceptance Criteria: MCP Test Framework\n")
    assert "- Idea ID: bu-test001" in first
    assert "- Workflow context: pre-release CI validation" in first
    assert "## Functional Criteria" in first
    assert "### AC-F1: Problem workflow" in first
    assert (
        "- Statement: The implementation addresses the stated problem: "
        "No standard way to test MCP servers"
    ) in first
    assert "### AC-NF4: Evidence traceability" in first
    assert "### EC6: Known weakness path" in first
    assert (
        "Do not expand scope to solve this evaluation weakness without approval: "
        "Niche audience"
    ) in first
    assert "## Evidence Links" in first
    assert "### ins-test001" in first
    assert "- URI: insights://ins-test001" in first
    assert "### sig-test001" in first
    assert "- URI: signals://sig-test001" in first
    assert "## Review Checklist" in first
    assert "### RC4" in first


def test_render_acceptance_criteria_markdown_handles_sparse_optional_fields(sample_unit):
    sparse_unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "validation_plan": "",
            "inspiring_insights": [],
            "evidence_signals": [],
            "source_idea_ids": [],
            "domain_risks": [],
            "composability_notes": "",
        }
    )
    criteria = generate_acceptance_criteria(sparse_unit)

    markdown = render_acceptance_criteria_markdown(criteria)

    assert markdown.endswith("\n")
    assert "- Recommendation: none" in markdown
    assert "- Evidence density available: False" in markdown
    assert "### EC4: Ambiguous persona" in markdown
    assert "## Evidence Links\n\nNone.\n" in markdown

    minimal_markdown = render_acceptance_criteria_markdown({"summary": {"title": ""}})
    assert minimal_markdown.startswith("# Acceptance Criteria: Untitled Idea\n")
    assert "- Schema version: none" in minimal_markdown
    assert "## Functional Criteria\n\nNone.\n" in minimal_markdown
    assert minimal_markdown.endswith("\n")
