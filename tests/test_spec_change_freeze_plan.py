"""Tests for TactSpec change freeze plan generation."""

from __future__ import annotations

import csv
import io

from max.spec import generate_change_freeze_plan, render_change_freeze_plan_csv, render_change_freeze_plan_markdown
from max.spec.change_freeze_plan import CHANGE_FREEZE_PLAN_CSV_COLUMNS
from max.spec.generator import generate_spec_preview


def test_change_freeze_plan_shape_and_renderers(sample_unit, sample_evaluation) -> None:
    plan = generate_change_freeze_plan(generate_spec_preview(sample_unit, sample_evaluation))

    assert plan["kind"] == "max.change_freeze_plan"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "freeze_windows",
        "allowed_exceptions",
        "approval_paths",
        "dependency_checks",
        "thaw_criteria",
        "evidence_references",
    }
    assert plan["summary"]["strictness"] == "strict"
    assert plan["approval_paths"][1]["severity"] == "required"

    markdown = render_change_freeze_plan_markdown(plan)
    assert "# MCP Test Framework Change Freeze Plan" in markdown
    assert "## Freeze Windows" in markdown
    assert "## Thaw Criteria" in markdown

    csv_text = render_change_freeze_plan_csv(plan)
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert csv_text.splitlines()[0] == ",".join(CHANGE_FREEZE_PLAN_CSV_COLUMNS)
    assert [row["section"] for row in rows[:2]] == ["freeze_windows", "freeze_windows"]
    assert any(row["section"] == "approval_paths" and row["name"] == "sponsor_approval" for row in rows)


def test_change_freeze_plan_sparse_defaults() -> None:
    plan = generate_change_freeze_plan({})

    assert plan["summary"]["strictness"] == "standard"
    assert plan["summary"]["title"] == "Untitled TactSpec"
    assert plan["approval_paths"][1]["severity"] == "conditional"
