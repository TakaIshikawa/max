from __future__ import annotations

import json

from max.spec import generate_data_residency_exception_plan


def test_data_residency_exception_plan_renders_scope_and_controls() -> None:
    plan = generate_data_residency_exception_plan(
        _spec(
            "data_residency_exception",
            {
                "exceptions": [
                    {"request": "EU logs in us-east-1", "region": "EU -> US", "data_class": "support logs", "severity": "high", "expiry": "2026-06-30"},
                    {"request": "APAC analytics replay", "region": "APAC -> US", "severity": "low"},
                ],
                "regions": ["EU -> US"],
                "customers": [{"customer": "enterprise", "data_class": "support logs"}],
                "compensating_controls": ["field encryption"],
                "approvers": ["privacy counsel"],
                "monitoring": ["regional transfer dashboard"],
                "expiration": ["30 day exception expiry"],
                "remediation": ["move processing back to EU"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.data_residency_exception_plan.v1"
    assert [item["name"] for item in plan["exception_scope"]] == ["EU logs in us-east-1", "APAC analytics replay"]
    assert set(plan) >= {"affected_regions", "customer_data_classes", "compensating_controls", "approval_gates", "expiration_reviews", "rollback_remediation"}
    assert json.loads(json.dumps(plan)) == plan


def test_data_residency_exception_plan_defaults_sparse_input() -> None:
    plan = generate_data_residency_exception_plan({})

    assert plan["exception_scope"][0]["owner"] == "privacy_owner"
    assert plan["monitoring"][0]["name"] == "residency transfer monitoring and customer impact review"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["dre-1"]}}
