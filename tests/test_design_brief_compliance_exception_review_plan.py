from __future__ import annotations

import json

from max.analysis.design_brief_compliance_exception_review_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_compliance_exception_review_plan,
)


def test_compliance_exception_review_plan_normalizes_complete_input() -> None:
    plan = generate_design_brief_compliance_exception_review_plan(
        {
            "metadata": {
                "compliance_exception_review_plan": {
                    "exceptions": [
                        {"name": "PCI logging gap", "owner": "GRC", "evidence": ["EV2", "EV1"]},
                        {"name": "Audit export delay", "owner": "Security", "evidence": ["EV1"]},
                    ],
                    "owners": [{"name": "CISO", "role": "approver", "evidence": ["EV3"]}],
                    "review_cadence": "weekly",
                    "compensating_controls": [{"name": "manual audit", "owner": "GRC", "evidence": ["EV2"]}],
                    "evidence_references": ["EV1", "ev1"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["name"] for row in plan["exception_rows"]] == [
        "Audit export delay",
        "PCI logging gap",
    ]
    assert plan["review_cadence"]["cadence"] == "weekly"
    assert plan["evidence_references"] == ["EV1", "EV2", "EV3"]
    assert json.loads(json.dumps(plan)) == plan


def test_compliance_exception_review_plan_sparse_input_reports_high_gaps() -> None:
    plan = generate_design_brief_compliance_exception_review_plan({})

    assert [gap["id"] for gap in plan["readiness_gaps"]] == [
        "missing_compliance_exceptions",
        "missing_exception_owners",
        "missing_review_cadence",
    ]
    assert {gap["severity"] for gap in plan["readiness_gaps"]} == {"high"}
    assert json.loads(json.dumps(plan)) == plan
