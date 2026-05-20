from __future__ import annotations

import json

from max.analysis.design_brief_risk_acceptance_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_risk_acceptance_plan,
)


def test_risk_acceptance_plan_normalizes_risks_and_summary() -> None:
    plan = generate_design_brief_risk_acceptance_plan(
        {
            "metadata": {
                "risk_acceptance_plan": {
                    "risks": [
                        {"risk": "Vendor outage", "owner": "COO", "status": "expired", "expiry": "2026-01-01", "mitigation": "backup queue", "evidence": ["EV2"]},
                        {"risk": "Audit delay", "owner": "CISO", "status": "accepted", "expiry": "2026-06-30", "mitigation": "manual review", "evidence": ["EV1", "EV1"]},
                        {"risk": "Migration drift", "owner": "CTO", "status": "pending", "mitigation": "daily compare"},
                    ],
                    "approval_evidence": ["EV0"],
                }
            }
        }
    )

    assert plan["kind"] == KIND
    assert plan["schema_version"] == SCHEMA_VERSION
    assert [row["risk"] for row in plan["risk_rows"]] == ["Audit delay", "Migration drift", "Vendor outage"]
    assert plan["summary"] == {"accepted_count": 1, "pending_count": 1, "expired_count": 1, "gap_count": 0}
    assert plan["approval_evidence"] == ["EV0", "EV1", "EV2"]
    assert json.loads(json.dumps(plan)) == plan


def test_risk_acceptance_plan_reports_sparse_gaps() -> None:
    plan = generate_design_brief_risk_acceptance_plan({})

    assert [gap["id"] for gap in plan["readiness_gaps"]] == ["missing_risks", "missing_decision_owners"]
    assert json.loads(json.dumps(plan)) == plan
