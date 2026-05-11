from __future__ import annotations

import csv
from io import StringIO

from max.spec.change_freeze_plan import (
    CHANGE_FREEZE_PLAN_CSV_COLUMNS,
    CHANGE_FREEZE_PLAN_SCHEMA_VERSION,
    generate_change_freeze_plan,
    render_change_freeze_plan_csv,
    render_change_freeze_plan_markdown,
)


def test_change_freeze_plan_shape_markdown_and_csv() -> None:
    plan = generate_change_freeze_plan(_tact_spec())
    markdown = render_change_freeze_plan_markdown(plan)
    rows = list(csv.DictReader(StringIO(render_change_freeze_plan_csv(plan))))

    assert plan["schema_version"] == CHANGE_FREEZE_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.change_freeze_plan"
    assert {"freeze_windows", "allowed_exceptions", "approval_paths", "dependency_checks", "thaw_criteria", "evidence_references"} <= set(plan)
    assert plan["freeze_windows"][0]["timing"] == "48 hours before launch"
    assert "## Freeze Windows" in markdown
    assert "## Allowed Exceptions" in markdown
    assert render_change_freeze_plan_csv(plan).splitlines()[0] == ",".join(CHANGE_FREEZE_PLAN_CSV_COLUMNS)
    assert [row["section"] for row in rows[:2]] == ["freeze_windows", "freeze_windows"]


def _tact_spec() -> dict:
    return {"source": {"idea_id": "bu-freeze"}, "project": {"title": "Payments Launch", "buyer": "CFO", "specific_user": "billing operator", "workflow_context": "payment review"}, "solution": {"suggested_stack": {"database": "Postgres"}}, "execution": {"validation_plan": "Run payment smoke tests.", "risks": ["payment outage risk"]}}
