"""Tests for spec-side implementation plan generation."""

from __future__ import annotations

import json

from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import (
    IMPLEMENTATION_PLAN_SCHEMA_VERSION,
    generate_implementation_plan,
    render_implementation_plan_markdown,
)


def test_generate_implementation_plan_structures_agent_handoff(sample_unit, sample_evaluation):
    spec_preview = generate_spec_preview(sample_unit, sample_evaluation)

    plan = generate_implementation_plan(sample_unit, sample_evaluation, spec_preview)

    assert plan["schema_version"] == IMPLEMENTATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.implementation_plan"
    assert plan["idea_id"] == "bu-test001"
    assert plan["source"]["spec_preview_schema_version"] == "tact-spec-preview/v1"
    assert plan["summary"]["title"] == "MCP Test Framework"
    assert plan["summary"]["recommendation"] == "yes"
    assert [milestone["id"] for milestone in plan["milestones"]] == ["M1", "M2", "M3", "M4"]
    assert [task["id"] for task in plan["task_breakdown"]] == [
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
        "T7",
        "T8",
        "T9",
    ]
    assert any(item["path"] == "src/cli.ts" for item in plan["expected_files_modules"])
    assert any(
        step["description"] == sample_unit.validation_plan
        for step in plan["validation_steps"]
    )
    assert any(risk["description"] == "protocol churn" for risk in plan["risks"])


def test_generate_implementation_plan_is_json_serializable(sample_unit, sample_evaluation):
    plan = generate_implementation_plan(sample_unit, sample_evaluation)

    assert json.loads(json.dumps(plan))["kind"] == "max.implementation_plan"


def test_generate_implementation_plan_surfaces_open_questions_for_sparse_idea(sample_unit):
    sparse_unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "buyer": "",
            "workflow_context": "",
            "validation_plan": "",
            "first_10_customers": "",
            "suggested_stack": {},
            "domain_risks": [],
        }
    )

    plan = generate_implementation_plan(sparse_unit)

    assert plan["summary"]["recommendation"] is None
    assert (
        "Which specific user persona should the MVP optimize for first?"
        in plan["open_questions"]
    )
    assert any(risk["source"] == "evaluation" for risk in plan["risks"])


def test_render_implementation_plan_markdown_is_stable_and_traceable(
    sample_unit,
    sample_evaluation,
):
    spec_preview = generate_spec_preview(sample_unit, sample_evaluation)
    plan = generate_implementation_plan(sample_unit, sample_evaluation, spec_preview)

    first = render_implementation_plan_markdown(plan)
    second = render_implementation_plan_markdown(plan)

    assert first == second
    assert first.endswith("\n")
    assert first.startswith("# Implementation Plan: MCP Test Framework\n")
    assert "- Schema version: max-implementation-plan/v1" in first
    assert "- Idea ID: bu-test001" in first
    assert "- Spec preview schema: tact-spec-preview/v1" in first
    assert "- Workflow context: pre-release CI validation" in first
    assert "## Milestones" in first
    assert "### M1: Spec Alignment" in first
    assert "### M2: MVP Implementation" in first
    assert "##### T4" in first
    assert "- Depends on: `T3`" in first
    assert "### `src/cli.ts`" in first
    assert "## Validation Steps" in first
    assert f"- Description: {sample_unit.validation_plan}" in first
    assert "## Risks" in first
    assert "- Description: protocol churn" in first
    assert "- Mitigation: Address during MVP scope and validation." in first
    assert "## Agent Handoff" in first
    assert "### Definition of Done" in first


def test_render_implementation_plan_markdown_preserves_ordering(sample_unit, sample_evaluation):
    plan = generate_implementation_plan(sample_unit, sample_evaluation)

    markdown = render_implementation_plan_markdown(plan)

    assert markdown.index("### M1: Spec Alignment") < markdown.index("### M2: MVP Implementation")
    assert markdown.index("### M2: MVP Implementation") < markdown.index(
        "### M3: Validation Harness"
    )
    assert markdown.index("### M3: Validation Harness") < markdown.index("### M4: Release Handoff")
    assert markdown.index("##### T1") < markdown.index("##### T2")
    assert markdown.index("##### T3") < markdown.index("##### T4")
    assert markdown.index("##### T8") < markdown.index("##### T9")


def test_render_implementation_plan_markdown_handles_sparse_optional_fields(sample_unit):
    sparse_unit = sample_unit.model_copy(
        update={
            "specific_user": "",
            "buyer": "",
            "workflow_context": "",
            "validation_plan": "",
            "first_10_customers": "",
            "suggested_stack": {},
            "domain_risks": [],
        }
    )
    plan = generate_implementation_plan(sparse_unit)

    markdown = render_implementation_plan_markdown(plan)

    assert markdown.endswith("\n")
    assert "- Recommendation: none" in markdown
    assert "- Workflow context: none" in markdown
    assert "- Depends on: none" in markdown
    assert "## Open Questions" in markdown
    assert "- Which specific user persona should the MVP optimize for first?" in markdown
    assert "### evaluation" in markdown
    assert "- Description: No utility evaluation is available for this idea." in markdown

    minimal_markdown = render_implementation_plan_markdown({"summary": {"title": ""}})
    assert minimal_markdown.startswith("# Implementation Plan: Untitled Idea\n")
    assert "- Schema version: none" in minimal_markdown
    assert "## Milestones\n\nNone.\n" in minimal_markdown
    assert "## Agent Handoff\n\nNone.\n" in minimal_markdown
    assert minimal_markdown.endswith("\n")


def test_render_implementation_plan_markdown_includes_owner_and_timeline_fields():
    plan = {
        "summary": {"title": "Owner Timeline Test"},
        "milestones": [
            {
                "id": "M1",
                "title": "Build",
                "goal": "Ship the handoff.",
                "owner": "agent",
                "timeline": "day 1",
                "tasks": [
                    {
                        "id": "T1",
                        "description": "Implement renderer.",
                        "acceptance": "Markdown renders.",
                        "depends_on": [],
                        "expected_files_modules": ["src/max/spec/implementation_plan.py"],
                        "suggested_owner": "codex",
                        "due_date": "2026-05-04",
                    }
                ],
                "validation": ["Run implementation plan tests."],
                "expected_files_modules": ["src/max/spec/implementation_plan.py"],
            }
        ],
    }

    markdown = render_implementation_plan_markdown(plan)

    assert "- Owner: agent" in markdown
    assert "- Timeline: day 1" in markdown
    assert "- Suggested owner: codex" in markdown
    assert "- Due date: 2026-05-04" in markdown
