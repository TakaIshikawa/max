from __future__ import annotations

import json

from max.analysis import generate_design_brief_migration_readiness_plan as exported_generate
from max.analysis.design_brief_migration_readiness_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_migration_readiness_plan,
)


def test_migration_readiness_plan_sorts_cohorts_and_includes_checks() -> None:
    brief = {
        "metadata": {
            "migration_readiness_plan": {
                "cohorts": [
                    {"name": "Wave 2", "source": "legacy", "target": "v2", "rollback": "restore snapshot", "owner": "eng", "evidence": ["runbook"]},
                    {"name": "Wave 1", "source_environment": "legacy", "target_environment": "v2", "rollback_plan": "dual write pause", "owner": "ops", "evidence": ["pilot"]},
                ],
                "communications": ["email notice"],
                "validation_checks": ["record counts", "login success"],
            }
        }
    }

    plan = generate_design_brief_migration_readiness_plan(brief)

    assert plan == generate_design_brief_migration_readiness_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [row["cohort"] for row in plan["migration_cohorts"]] == ["Wave 1", "Wave 2"]
    assert plan["validation_checks"] == ["login success", "record counts"]
    assert plan["summary"]["readiness_status"] == "ready"
    assert exported_generate({})["kind"] == KIND


def test_migration_readiness_plan_blockers_rollback_and_validation_gaps_affect_status() -> None:
    plan = generate_design_brief_migration_readiness_plan(
        {"migration_readiness_plan": {"cohorts": [{"name": "Wave 1", "source": "legacy"}], "blockers": [{"blocker": "missing archive"}]}}
    )

    assert plan["summary"]["readiness_status"] == "blocked"
    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_validation_checks",
        "wave_1_missing_rollback_plan",
        "wave_1_missing_environment_mapping",
        "missing_archive_missing_owner",
    ]
