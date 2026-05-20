from __future__ import annotations

import json

from max.analysis.design_brief_data_quality_remediation_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_data_quality_remediation_plan,
)


def test_data_quality_remediation_plan_normalizes_complete_input() -> None:
    plan = generate_design_brief_data_quality_remediation_plan(
        {
            "metadata": {
                "data_quality_remediation_plan": {
                    "defect_classes": [
                        {"name": "duplicate accounts", "severity": "medium", "owner": "Data"},
                        {"name": "bad emails", "severity": "high", "owner": "CRM", "evidence": ["EV1"]},
                    ],
                    "affected_datasets": [{"name": "accounts"}],
                    "remediation_owners": [{"name": "CRM"}],
                    "validation_checks": [{"name": "email regex", "owner": "QA"}],
                    "due_dates": ["2026-08-01", "2026-07-15"],
                    "evidence": ["EV1"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["defect_classes"]] == ["bad emails", "duplicate accounts"]
    assert plan["due_dates"] == ["2026-07-15", "2026-08-01"]
    assert plan["summary"]["gap_count"] == 0
    assert json.loads(json.dumps(plan)) == plan


def test_data_quality_remediation_plan_reports_high_severity_gaps() -> None:
    plan = generate_design_brief_data_quality_remediation_plan(
        {"data_quality_remediation_plan": {"defect_classes": [{"name": "orphan invoices", "severity": "high"}]}}
    )

    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_validation_checks",
        "orphan invoices_missing_owner",
        "orphan invoices_missing_validation",
    ]
    assert json.loads(json.dumps(plan)) == plan
