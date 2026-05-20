from __future__ import annotations

import json

from max.analysis import generate_design_brief_contract_renewal_risk_plan as exported_generate
from max.analysis.design_brief_contract_renewal_risk_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_design_brief_contract_renewal_risk_plan,
)


def test_contract_renewal_risk_plan_is_stable_and_sorted() -> None:
    brief = {
        "metadata": {
            "contract_renewal_risk_plan": {
                "renewal_accounts": [
                    {"account": "BetaCo", "renewal_date": "2026-09-01", "risk_level": "low", "success_criteria": ["usage stable"], "mitigation_owner": "cs", "evidence": ["crm"]},
                    {"account": "Acme", "renewal_date": "2026-06-01", "risk_level": "high", "risk_drivers": ["adoption"], "success_criteria": ["exec sponsor"], "mitigation_owner": "sales", "evidence": ["qbr"]},
                ]
            }
        }
    }

    plan = generate_design_brief_contract_renewal_risk_plan(brief)

    assert plan == generate_design_brief_contract_renewal_risk_plan(brief)
    assert json.loads(json.dumps(plan)) == plan
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert [row["account"] for row in plan["renewal_risks"]] == ["Acme", "BetaCo"]
    assert plan["summary"]["readiness_status"] == "ready"
    assert exported_generate({})["kind"] == KIND


def test_contract_renewal_risk_plan_reports_missing_owner_date_and_criteria() -> None:
    plan = generate_design_brief_contract_renewal_risk_plan(
        {"contract_renewal_risk_plan": {"accounts": [{"name": "Acme", "risk_level": "high"}]}}
    )

    assert plan["summary"]["readiness_status"] == "blocked"
    assert [gap["id"] for gap in plan["renewal_gaps"]] == [
        "acme_missing_renewal_date",
        "acme_missing_success_criteria",
        "acme_missing_mitigation_owner",
    ]
