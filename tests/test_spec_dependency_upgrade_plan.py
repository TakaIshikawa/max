from __future__ import annotations

import csv
from io import StringIO

from max.spec.dependency_upgrade_plan import (
    DEPENDENCY_UPGRADE_PLAN_CSV_COLUMNS,
    DEPENDENCY_UPGRADE_PLAN_SCHEMA_VERSION,
    generate_dependency_upgrade_plan,
    render_dependency_upgrade_plan_csv,
    render_dependency_upgrade_plan_markdown,
)


def test_dependency_upgrade_plan_shape() -> None:
    plan = generate_dependency_upgrade_plan(_spec("routine maintenance", False))
    rows = list(csv.DictReader(StringIO(render_dependency_upgrade_plan_csv(plan))))

    assert plan["schema_version"] == DEPENDENCY_UPGRADE_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.dependency_upgrade_plan"
    assert {"dependency_list", "upgrade_rationale", "affected_surfaces", "compatibility_checks", "test_matrix", "rollout_sequence", "rollback", "evidence"} <= set(plan)
    assert plan["summary"]["dependency_count"] == 2
    assert plan["summary"]["security_driven"] is False
    assert "## Test Matrix" in render_dependency_upgrade_plan_markdown(plan)
    assert render_dependency_upgrade_plan_csv(plan).splitlines()[0] == ",".join(DEPENDENCY_UPGRADE_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "dependency_list"


def test_dependency_upgrade_plan_highlights_security_upgrades() -> None:
    plan = generate_dependency_upgrade_plan(_spec("security CVE fix", True))

    assert plan["summary"]["security_driven"] is True
    assert plan["dependency_list"][0]["severity"] == "high"
    assert "Prioritize security-driven" in plan["upgrade_rationale"][0]["action"]


def _spec(reason: str, security: bool) -> dict:
    return {"source": {"idea_id": "dep-up"}, "project": {"workflow_context": "api worker"}, "dependency_upgrade": {"dependencies": ["urllib3", "requests"], "reason": reason, "security": security, "affected_services": ["api", "worker"]}}
