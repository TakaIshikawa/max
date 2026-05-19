from __future__ import annotations

import csv
from io import StringIO

from max.spec.tenant_migration_plan import (
    TENANT_MIGRATION_PLAN_CSV_COLUMNS,
    TENANT_MIGRATION_PLAN_SCHEMA_VERSION,
    generate_tenant_migration_plan,
    render_tenant_migration_plan_csv,
    render_tenant_migration_plan_markdown,
)


def test_tenant_migration_plan_shape_and_defaults() -> None:
    plan = generate_tenant_migration_plan({"source": {"idea_id": "tenant-default"}, "project": {"workflow_context": "tenant move"}})
    rows = list(csv.DictReader(StringIO(render_tenant_migration_plan_csv(plan))))

    assert plan["schema_version"] == TENANT_MIGRATION_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.tenant_migration_plan"
    assert {"tenant_eligibility", "environments", "migration_window", "data_copy_steps", "validation_checks", "communications", "rollback", "evidence"} <= set(plan)
    assert plan["summary"]["tenant"] == "tenant-default"
    assert plan["summary"]["explicit_approval_required"] is False
    assert "## Data Copy Steps" in render_tenant_migration_plan_markdown(plan)
    assert render_tenant_migration_plan_csv(plan).splitlines()[0] == ",".join(TENANT_MIGRATION_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "tenant_eligibility"


def test_tenant_migration_plan_requires_approval_for_downtime() -> None:
    plan = generate_tenant_migration_plan({"tenant_migration": {"tenant_id": "acme", "customer_facing_downtime": True}})

    assert plan["summary"]["explicit_approval_required"] is True
    assert plan["migration_window"][0]["severity"] == "high"
    assert "explicit approval" in plan["migration_window"][0]["action"]
