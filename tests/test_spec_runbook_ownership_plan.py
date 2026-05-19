from __future__ import annotations

import csv
from io import StringIO

from max.spec.runbook_ownership_plan import (
    RUNBOOK_OWNERSHIP_PLAN_CSV_COLUMNS,
    RUNBOOK_OWNERSHIP_PLAN_SCHEMA_VERSION,
    generate_runbook_ownership_plan,
    render_runbook_ownership_plan_csv,
    render_runbook_ownership_plan_markdown,
)


def test_runbook_ownership_plan_shape() -> None:
    plan = generate_runbook_ownership_plan({"source": {"idea_id": "rbk"}, "project": {"workflow_context": "billing alerts"}, "runbook": {"name": "Billing Alerts", "owner": "ops", "last_reviewed": "2026-05-01", "publication_status": "published"}})
    rows = list(csv.DictReader(StringIO(render_runbook_ownership_plan_csv(plan))))

    assert plan["schema_version"] == RUNBOOK_OWNERSHIP_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.runbook_ownership_plan"
    assert {"runbook_inventory", "owners", "escalation_paths", "stale_sections", "review_cadence", "validation_drills", "handoff_evidence", "publication_state"} <= set(plan)
    assert plan["summary"]["readiness_risk"] is False
    assert "## Validation Drills" in render_runbook_ownership_plan_markdown(plan)
    assert render_runbook_ownership_plan_csv(plan).splitlines()[0] == ",".join(RUNBOOK_OWNERSHIP_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "runbook_inventory"


def test_runbook_ownership_plan_flags_missing_owner_and_stale_review() -> None:
    plan = generate_runbook_ownership_plan({"runbook": {"name": "Checkout", "last_reviewed": ""}})

    assert plan["summary"]["readiness_risk"] is True
    assert plan["owners"][0]["severity"] == "critical"
    assert plan["stale_sections"][0]["severity"] == "high"
