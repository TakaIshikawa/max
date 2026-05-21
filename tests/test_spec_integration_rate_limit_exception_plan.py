from __future__ import annotations

import json

from max.spec import generate_integration_rate_limit_exception_plan


def test_integration_rate_limit_exception_plan_sorts_risks() -> None:
    plan = generate_integration_rate_limit_exception_plan(
        _spec(
            "integration_rate_limit_exception",
            {
                "integrations": [
                    {"name": "Search API", "severity": "low", "status": "ready", "requested_limit": "100 rps"},
                    {"name": "Billing API", "severity": "high", "status": "overdue", "duration": "7 days"},
                ],
                "consumers": ["Acme"],
                "mitigation_controls": ["burst alerts"],
                "approval_gates": ["platform approval"],
                "monitoring": ["429 dashboard"],
                "rollback_criteria": ["restore baseline"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.integration_rate_limit_exception_plan.v1"
    assert [item["name"] for item in plan["rate_limit_exceptions"]] == ["Billing API", "Search API"]
    assert plan["rate_limit_exceptions"][1]["duration"] == "30 days"
    assert plan["mitigation_controls"][0]["evidence_reference_ids"] == ["EV1"]
    assert set(plan) >= {"consumer_impact", "approval_gates", "monitoring", "rollback_criteria"}
    assert json.loads(json.dumps(plan)) == plan


def test_integration_rate_limit_exception_plan_defaults_sparse_input() -> None:
    plan = generate_integration_rate_limit_exception_plan({})

    assert plan["rate_limit_exceptions"][0]["duration"] == "30 days"
    assert plan["rollback_criteria"][0]["name"] == "restore standard limit"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["rate-1"]}}
