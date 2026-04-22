"""Tests for spec-side implementation plan generation."""

from __future__ import annotations

import json

from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import (
    IMPLEMENTATION_PLAN_SCHEMA_VERSION,
    generate_implementation_plan,
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
    assert any(step["description"] == sample_unit.validation_plan for step in plan["validation_steps"])
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
    assert "Which specific user persona should the MVP optimize for first?" in plan["open_questions"]
    assert any(risk["source"] == "evaluation" for risk in plan["risks"])
