"""Tests for TactSpec data migration rehearsal plan generation."""

from __future__ import annotations

import csv
import io

from max.spec import (
    generate_data_migration_rehearsal_plan,
    render_data_migration_rehearsal_plan_csv,
    render_data_migration_rehearsal_plan_markdown,
)
from max.spec.data_migration_rehearsal_plan import DATA_MIGRATION_REHEARSAL_PLAN_CSV_COLUMNS
from max.spec.generator import generate_spec_preview


def test_data_migration_rehearsal_plan_shape_and_risk_depth(sample_unit, sample_evaluation) -> None:
    tact_spec = generate_spec_preview(sample_unit, sample_evaluation)
    tact_spec["execution"]["risks"] = ["data loss during migration"]
    plan = generate_data_migration_rehearsal_plan(tact_spec)

    assert plan["kind"] == "max.data_migration_rehearsal_plan"
    assert set(plan) == {
        "schema_version",
        "kind",
        "source",
        "summary",
        "rehearsal_stages",
        "fixture_requirements",
        "validation_queries",
        "reconciliation_checks",
        "cutover_gates",
        "rollback_rehearsals",
        "evidence_references",
    }
    assert plan["summary"]["rehearsal_depth"] == "deep"
    assert plan["cutover_gates"][1]["severity"] == "required"


def test_data_migration_rehearsal_plan_renderers() -> None:
    plan = generate_data_migration_rehearsal_plan({"project": {"title": "Sparse Migration"}})
    markdown = render_data_migration_rehearsal_plan_markdown(plan)
    csv_text = render_data_migration_rehearsal_plan_csv(plan)
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert plan["summary"]["rehearsal_depth"] == "standard"
    assert "# Sparse Migration Data Migration Rehearsal Plan" in markdown
    assert "## Validation Queries" in markdown
    assert csv_text.splitlines()[0] == ",".join(DATA_MIGRATION_REHEARSAL_PLAN_CSV_COLUMNS)
    assert any(row["section"] == "rollback_rehearsals" for row in rows)
