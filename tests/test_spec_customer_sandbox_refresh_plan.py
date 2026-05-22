from __future__ import annotations

import json

from max.spec import generate_customer_sandbox_refresh_plan


def test_customer_sandbox_refresh_plan_includes_privacy_timing_and_cleanup() -> None:
    plan = generate_customer_sandbox_refresh_plan(
        _spec(
            "customer_sandbox_refresh",
            {
                "tenants": [{"tenant": "acme-demo", "severity": "high"}, {"tenant": "beta-demo", "severity": "low"}],
                "source_snapshot": ["prod snapshot 2026-05-01"],
                "masking": ["mask emails"],
                "window": ["Saturday 02:00 UTC"],
                "validation": ["login and masking check"],
                "notifications": ["customer notice"],
                "rollback": ["restore old sandbox"],
                "cleanup": ["delete export files"],
            },
        )
    )

    assert plan["schema_version"] == "max.spec.customer_sandbox_refresh_plan.v1"
    assert [item["name"] for item in plan["refresh_scope"]] == ["acme-demo", "beta-demo"]
    assert set(plan) >= {"source_snapshot", "masking_requirements", "timing_window", "validation_checks", "stakeholder_notifications", "rollback", "cleanup"}
    assert json.loads(json.dumps(plan)) == plan


def test_customer_sandbox_refresh_plan_defaults_notifications_and_validation() -> None:
    plan = generate_customer_sandbox_refresh_plan({})

    assert plan["validation_checks"][0]["name"] == "login, data shape, integration, and masking validation"
    assert plan["stakeholder_notifications"][0]["name"] == "customer and internal refresh notice"


def _spec(key: str, hints: dict) -> dict:
    return {"metadata": {key: hints}, "evidence": {"source_idea_ids": ["csr-1"]}}
