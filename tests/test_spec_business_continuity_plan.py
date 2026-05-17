from __future__ import annotations

from max.spec.business_continuity_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_business_continuity_plan,
)
from max.spec import generate_business_continuity_plan as exported_generate


def test_business_continuity_plan_baseline() -> None:
    plan = generate_business_continuity_plan(
        {"critical_functions": ["support triage"], "dependencies": ["Zendesk"]}
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["critical_functions"] == ["support triage"]
    assert plan["dependencies"] == ["Zendesk"]
    assert plan["communication_channels"]["level"] == "standard"
    assert plan["communication_channels"]["executive"] == "daily summary"
    assert plan["recovery_priorities"] == [{"rank": 1, "function": "support triage", "target": "0-2 hours"}]
    assert plan["review_cadence"] == "annual"
    assert plan["continuity_procedures"][0]["owner"] == "Continuity lead"
    assert "manual workaround log and customer-impact notes" in plan["evidence"]
    assert "staffing roster with primary and backup coverage" in plan["evidence"]


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
    assert plan["communication_channels"]["level"] == "escalated"
    assert plan["communication_channels"]["customer"] == "customer status page and account team updates"
    assert plan["communication_channels"]["executive"] == "hourly executive updates"
    assert plan["review_cadence"] == "semiannual"
    assert plan["recovery_priorities"] == [
        {"rank": 1, "function": "payments intake", "target": "0-1 hour"},
        {"rank": 2, "function": "customer support", "target": "0-4 hours"},
    ]
    assert plan["manual_workarounds"] == ["phone-assisted order capture"]


def test_business_continuity_plan_is_importable_from_spec_package() -> None:
    plan = exported_generate({"critical_functions": ["incident response"]})

    assert plan["critical_functions"] == ["incident response"]
