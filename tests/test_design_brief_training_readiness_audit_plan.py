from __future__ import annotations

import json

from max.analysis.design_brief_training_readiness_audit_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_training_readiness_audit_plan,
)


def test_training_readiness_audit_plan_normalizes_complete_input() -> None:
    plan = generate_design_brief_training_readiness_audit_plan(
        {
            "metadata": {
                "training_readiness_audit_plan": {
                    "learner_cohorts": [{"name": "admins"}, {"name": "agents"}],
                    "training_assets": [{"name": "runbook video", "owner": "Enablement"}],
                    "facilitators": [{"name": "trainer", "owner": "Enablement"}],
                    "completion_targets": [{"name": "admin complete", "target": "95%"}],
                    "assessment_checks": [{"name": "quiz pass", "owner": "Enablement", "evidence": ["EV1"]}],
                    "evidence": ["EV1", "EV2"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["learner_cohorts"]] == ["admins", "agents"]
    assert plan["summary"]["gap_count"] == 0
    assert json.loads(json.dumps(plan)) == plan


def test_training_readiness_audit_plan_reports_required_gaps() -> None:
    plan = generate_design_brief_training_readiness_audit_plan(
        {"training_readiness_audit_plan": {"assessment_checks": [{"name": "certification"}]}}
    )

    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_learner_cohorts",
        "missing_training_assets",
        "certification_missing_owner",
    ]
    assert json.loads(json.dumps(plan)) == plan
