from __future__ import annotations

import json

from max.analysis.design_brief_operational_runbook_review_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_operational_runbook_review_plan,
)


def test_operational_runbook_review_plan_normalizes_complete_input() -> None:
    plan = generate_design_brief_operational_runbook_review_plan(
        {
            "metadata": {
                "operational_runbook_review_plan": {
                    "runbook_sections": [{"name": "deploy", "owner": "SRE"}, {"name": "alerting", "owner": "Ops"}],
                    "owners": [{"name": "Ops", "role": "primary"}],
                    "escalation_paths": [{"name": "sev1", "owner": "Incident lead"}],
                    "drills": [{"name": "restore drill", "owner": "SRE", "evidence": ["EV1"]}],
                    "evidence": ["EV1"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["runbook_sections"]] == ["alerting", "deploy"]
    assert plan["summary"]["readiness_status"] == "ready"
    assert json.loads(json.dumps(plan)) == plan


def test_operational_runbook_review_plan_reports_missing_procedure_gaps() -> None:
    plan = generate_design_brief_operational_runbook_review_plan(
        {"operational_runbook_review_plan": {"missing_procedures": [{"name": "rollback", "severity": "high"}]}}
    )

    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_runbook_sections",
        "missing_runbook_owners",
        "rollback_missing_procedure",
    ]
    assert plan["summary"]["missing_procedure_count"] == 1
    assert json.loads(json.dumps(plan)) == plan
