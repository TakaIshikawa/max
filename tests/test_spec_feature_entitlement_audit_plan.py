from __future__ import annotations

import json

from max.spec import generate_feature_entitlement_audit_plan


def test_feature_entitlement_audit_plan_prioritizes_findings() -> None:
    plan = generate_feature_entitlement_audit_plan(
        _spec(
            "feature_entitlement_audit",
            {
                "scope": ["enterprise plans"],
                "expected_policy": ["paid plan required"],
                "findings": [
                    {"feature": "advanced export", "customer": "beta", "severity": "low"},
                    {"feature": "admin audit log", "customer": "acme", "severity": "high"},
                ],
                "impact": ["revenue leakage"],
                "remediation": ["disable unauthorized access"],
                "communications": ["account team notice"],
                "verification": ["entitlement recheck"],
                "prevention": ["daily drift job"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.feature_entitlement_audit_plan.v1"
    assert [item["name"] for item in plan["observed_exceptions"]] == ["admin audit log", "advanced export"]
    assert set(plan) >= {"entitlement_scope", "expected_policy", "impact_assessment", "remediation_owners", "customer_communications", "verification", "recurrence_prevention"}
    assert json.loads(json.dumps(plan)) == plan


def test_feature_entitlement_audit_plan_defaults_sparse_input() -> None:
    plan = generate_feature_entitlement_audit_plan({})

    assert plan["observed_exceptions"][0]["owner"] == "access_owner"
    assert plan["recurrence_prevention"][0]["name"] == "policy automation and recurring audit control"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"signal_ids": ["fea-1"]}}
