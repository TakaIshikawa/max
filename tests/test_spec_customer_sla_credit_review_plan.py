from __future__ import annotations

import json

from max.spec import generate_customer_sla_credit_review_plan


def test_customer_sla_credit_review_plan_sorts_breaches() -> None:
    plan = generate_customer_sla_credit_review_plan(
        _spec(
            "customer_sla_credit_review",
            {
                "affected_accounts": ["Acme", "Beta", "Acme"],
                "breach_records": [
                    {"name": "minor latency", "severity": "low", "credit_status": "ready"},
                    {"name": "outage credit", "severity": "critical", "credit_status": "missing"},
                    {"name": "response breach", "severity": "high", "credit_status": "overdue"},
                    {"name": "outage credit", "severity": "critical"},
                ],
                "credit_terms": ["99.9 SLA credit"],
                "finance_approvals": ["controller approval"],
                "customer_notices": ["account notice"],
                "remediation_links": ["incident review"],
                "validation_checks": ["credit calculation"],
            },
        )
    )

    assert [item["name"] for item in plan["affected_accounts"]] == ["Acme", "Beta"]
    assert [item["name"] for item in plan["breach_records"]] == [
        "outage credit",
        "response breach",
        "minor latency",
    ]
    assert plan["validation_checks"][0]["evidence_reference_ids"] == ["EV1"]
    assert json.loads(json.dumps(plan)) == plan


def test_customer_sla_credit_review_plan_defaults_sparse_input() -> None:
    plan = generate_customer_sla_credit_review_plan({})

    assert plan["affected_accounts"][0]["name"] == "launch sponsor"
    assert plan["breach_records"][0]["name"] == "SLA breach review"
    assert set(plan) >= {
        "credit_terms",
        "finance_approvals",
        "customer_notices",
        "remediation_links",
        "source",
        "evidence_references",
    }
    assert json.loads(json.dumps(plan)) == plan


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["idea-1"]}}
