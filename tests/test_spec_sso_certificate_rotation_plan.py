from __future__ import annotations

import json

from max.spec import generate_sso_certificate_rotation_plan


def test_sso_certificate_rotation_plan_prioritizes_expiry_and_includes_tests() -> None:
    plan = generate_sso_certificate_rotation_plan(
        _spec(
            "sso_certificate_rotation",
            {
                "certificates": [
                    {"tenant": "beta", "idp": "Okta", "expiry": "2026-12-01", "severity": "low"},
                    {"tenant": "acme", "idp": "Azure AD", "expiry": "expired", "severity": "critical"},
                    {"tenant": "zeon", "idp": "OneLogin", "expiry": "near expiry", "severity": "high"},
                ],
                "notices": ["customer admin notice"],
                "validation": ["successful login test"],
                "cutover": ["activate new cert"],
                "fallback": ["break-glass login"],
                "monitoring": ["login failure alert"],
                "rollback": ["restore previous cert"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.sso_certificate_rotation_plan.v1"
    assert [item["name"] for item in plan["idp_tenant_scope"]] == ["acme", "zeon", "beta"]
    assert plan["validation_windows"][0]["name"] == "successful login test"
    assert set(plan) >= {"certificate_details", "customer_notices", "cutover_steps", "fallback_access", "monitoring", "rollback"}
    assert json.loads(json.dumps(plan)) == plan


def test_sso_certificate_rotation_plan_defaults_sparse_input() -> None:
    plan = generate_sso_certificate_rotation_plan({})

    assert plan["idp_tenant_scope"][0]["owner"] == "identity_owner"
    assert plan["validation_windows"][0]["name"] == "successful SAML or OIDC login test and expired-certificate prevention check"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"insight_ids": ["sso-1"]}}
