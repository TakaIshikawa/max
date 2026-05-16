from __future__ import annotations

from max.spec.business_continuity_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_business_continuity_plan,
)


def test_business_continuity_plan_baseline() -> None:
    plan = generate_business_continuity_plan(
        {"critical_functions": ["support triage"], "dependencies": ["Zendesk"]}
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["critical_functions"] == ["support triage"]
    assert plan["dependencies"] == ["Zendesk"]
    assert plan["communication_channels"]["executive"] == "daily summary"
    assert plan["review_cadence"] == "annual"
    assert "manual workaround log and customer-impact notes" in plan["evidence"]


def test_business_continuity_plan_customer_facing_critical_function_escalates_comms() -> None:
    plan = generate_business_continuity_plan(
        {
            "criticality": "critical",
            "customer_facing": True,
            "critical_functions": "payments intake; customer support",
            "manual_workarounds": ["phone-assisted order capture"],
        }
    )

    assert plan["critical_functions"] == ["payments intake", "customer support"]
    assert plan["communication_channels"]["customer"] == "customer status page and account team updates"
    assert plan["communication_channels"]["executive"] == "hourly executive updates"
    assert plan["review_cadence"] == "semiannual"
    assert plan["manual_workarounds"] == ["phone-assisted order capture"]
