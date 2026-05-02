"""Tests for TactSpec migration checklist generation."""

from __future__ import annotations

import json

import pytest

from max.spec import generate_migration_checklist as exported_generate
from max.spec import render_migration_checklist_markdown as exported_render
from max.spec.generator import generate_spec_preview
from max.spec.migration_checklist import (
    KIND,
    MIGRATION_CHECKLIST_SCHEMA_VERSION,
    generate_migration_checklist,
    render_migration_checklist_markdown,
)
from max.types.buildable_unit import BuildableCategory, BuildableUnit


def test_generate_migration_checklist_has_stable_schema_shape(
    sample_unit, sample_evaluation
) -> None:
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)
    tact_spec["problem"]["current_workaround"] = "manual protocol testing in release branches"
    tact_spec["execution"]["risks"].append("Legacy CI jobs may keep running duplicate checks.")

    first = generate_migration_checklist(sample_unit, sample_evaluation, tact_spec)
    second = generate_migration_checklist(sample_unit, sample_evaluation, tact_spec)

    assert first == second
    assert first["schema_version"] == MIGRATION_CHECKLIST_SCHEMA_VERSION
    assert first["kind"] == KIND
    assert first["kind"] == "max.migration_checklist"
    assert first["idea_id"] == "bu-test001"
    assert first["source"]["evaluation_available"] is True
    assert first["source"]["tact_spec_available"] is True
    assert first["source"]["tact_spec_schema_version"] == "tact-spec-preview/v1"
    assert first["idea"]["recommendation"] == "yes"
    assert first["idea"]["suggested_stack"] == {"language": "typescript", "runtime": "node"}
    assert first["summary"]["migration_gate"] == "ready_for_migration_review"
    assert set(first) == {
        "schema_version",
        "kind",
        "idea_id",
        "source",
        "idea",
        "summary",
        "migration_assumptions",
        "pre_migration_tasks",
        "data_process_cutover_tasks",
        "rollback_checks",
        "stakeholder_communications",
        "evidence_references",
        "unresolved_gaps",
        "missing_inputs",
    }
    assert [item["id"] for item in first["migration_assumptions"]] == [
        "MA01",
        "MA02",
        "MA03",
        "MA04",
    ]
    assert [item["id"] for item in first["pre_migration_tasks"]] == [
        "PM01",
        "PM02",
        "PM03",
        "PM04",
    ]
    assert [item["id"] for item in first["data_process_cutover_tasks"]] == [
        "CT01",
        "CT02",
        "CT03",
        "CT04",
    ]
    assert [item["id"] for item in first["rollback_checks"]] == ["RB01", "RB02", "RB03"]
    assert [item["id"] for item in first["stakeholder_communications"]] == [
        "COM01",
        "COM02",
        "COM03",
    ]
    assert first["unresolved_gaps"] == []
    assert any(item["id"] == "signal:sig-test001" for item in first["evidence_references"])


def test_migration_checklist_derives_tasks_from_unit_solution_stack_risks_and_recommendation(
    sample_unit, sample_evaluation
) -> None:
    checklist = generate_migration_checklist(
        sample_unit, sample_evaluation, generate_spec_preview(sample_unit, sample_evaluation)
    )

    rendered_tasks = json.dumps(
        [
            *checklist["migration_assumptions"],
            *checklist["pre_migration_tasks"],
            *checklist["data_process_cutover_tasks"],
            *checklist["rollback_checks"],
            *checklist["stakeholder_communications"],
        ]
    )
    assert "manual protocol testing" in rendered_tasks
    assert "pre-release CI validation" in rendered_tasks
    assert "language=typescript, runtime=node" in rendered_tasks
    assert "protocol churn" in rendered_tasks
    assert "Niche audience" in rendered_tasks
    assert "recommendation is yes" in rendered_tasks
    assert "A CLI tool that validates MCP server implementations" in rendered_tasks


def test_generate_migration_checklist_is_json_serializable(sample_unit) -> None:
    checklist = generate_migration_checklist(sample_unit)

    assert json.loads(json.dumps(checklist))["idea_id"] == "bu-test001"


def test_generate_migration_checklist_degrades_for_sparse_inputs() -> None:
    sparse_unit = BuildableUnit(
        id="bu-sparse-migration",
        title="Sparse Migration Helper",
        one_liner="Help migrate a workflow",
        category=BuildableCategory.AUTOMATION,
        problem="Teams need help",
        solution="",
        value_proposition="",
    )

    checklist = generate_migration_checklist(sparse_unit)

    assert checklist["source"]["evaluation_available"] is False
    assert checklist["source"]["tact_spec_available"] is False
    assert checklist["idea"]["workflow_context"] == "Sparse Migration Helper workflow"
    assert checklist["idea"]["current_workaround"] == "current manual or incumbent workflow"
    assert checklist["summary"]["migration_gate"] == "migration_inputs_required"
    assert {gap["category"] for gap in checklist["unresolved_gaps"]} == {
        "missing_evaluation",
        "missing_tact_spec",
        "missing_workflow_context",
        "missing_current_workaround",
        "missing_risks",
        "missing_validation_plan",
        "missing_evidence_refs",
        "missing_stack",
    }
    assert "utility_evaluation" in checklist["missing_inputs"]
    assert checklist["migration_assumptions"][-1]["id"] == "MA05"
    assert checklist["rollback_checks"][2]["evidence_refs"] == [
        "GAP01",
        "GAP02",
        "GAP03",
        "GAP04",
        "GAP05",
        "GAP06",
        "GAP07",
        "GAP08",
    ]


def test_render_migration_checklist_markdown_has_required_sections(
    sample_unit, sample_evaluation
) -> None:
    checklist = generate_migration_checklist(
        sample_unit, sample_evaluation, generate_spec_preview(sample_unit, sample_evaluation)
    )

    first = render_migration_checklist_markdown(checklist)
    second = render_migration_checklist_markdown(checklist)

    assert first == second
    assert first.startswith("# MCP Test Framework Migration Checklist")
    assert f"- Schema version: {MIGRATION_CHECKLIST_SCHEMA_VERSION}" in first
    assert "- Kind: max.migration_checklist" in first
    assert "## Assumptions" in first
    assert "## Pre-Migration Tasks" in first
    assert "## Data and Process Cutover" in first
    assert "## Rollback" in first
    assert "## Communications" in first
    assert "## Evidence References" in first
    assert "## Gaps" in first
    assert "No unresolved migration gaps detected." in first
    assert "manual protocol testing" in first
    assert "{'" not in first
    assert "[{" not in first


def test_render_migration_checklist_markdown_rejects_unsupported_format(sample_unit) -> None:
    checklist = generate_migration_checklist(sample_unit)

    with pytest.raises(ValueError, match="Unsupported migration checklist render format: json"):
        render_migration_checklist_markdown(checklist, output_format="json")


def test_migration_checklist_exports(sample_unit) -> None:
    checklist = exported_generate(sample_unit)

    assert checklist["kind"] == "max.migration_checklist"
    assert exported_render(checklist).startswith("# MCP Test Framework Migration Checklist")
