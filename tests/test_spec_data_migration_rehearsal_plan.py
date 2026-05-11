from __future__ import annotations

import csv
from io import StringIO

from max.spec.data_migration_rehearsal_plan import (
    DATA_MIGRATION_REHEARSAL_PLAN_CSV_COLUMNS,
    DATA_MIGRATION_REHEARSAL_PLAN_SCHEMA_VERSION,
    generate_data_migration_rehearsal_plan,
    render_data_migration_rehearsal_plan_csv,
    render_data_migration_rehearsal_plan_markdown,
)


def test_data_migration_rehearsal_plan_shape_and_strict_cutover() -> None:
    plan = generate_data_migration_rehearsal_plan(_tact_spec())
    rows = list(csv.DictReader(StringIO(render_data_migration_rehearsal_plan_csv(plan))))

    assert plan["schema_version"] == DATA_MIGRATION_REHEARSAL_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.data_migration_rehearsal_plan"
    assert {"rehearsal_stages", "fixture_requirements", "validation_queries", "reconciliation_checks", "cutover_gates", "rollback_rehearsals", "evidence_references"} <= set(plan)
    assert plan["rehearsal_stages"][0]["timing"] == "T-5 days"
    assert plan["cutover_gates"][0]["action"] == "Required"
    assert "DRS1" in render_data_migration_rehearsal_plan_markdown(plan)
    assert render_data_migration_rehearsal_plan_csv(plan).splitlines()[0] == ",".join(DATA_MIGRATION_REHEARSAL_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "rehearsal_stages"


def _tact_spec() -> dict:
    return {"source": {"idea_id": "bu-migration"}, "project": {"title": "Account Migration", "specific_user": "account admin", "buyer": "ops director", "workflow_context": "account data cutover"}, "solution": {"technical_approach": "Migrate account records from CSV to Postgres."}, "execution": {"validation_plan": "Run reconciliation checks.", "risks": ["migration rollback and data loss risk"]}}
