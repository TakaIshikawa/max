from __future__ import annotations

from max.spec.change_management_plan import KIND, SCHEMA_VERSION, generate_change_management_plan


def test_change_management_plan_low_risk_change() -> None:
    plan = generate_change_management_plan(
        {
            "summary": "Update help text",
            "risk_level": "low",
            "environment": "staging",
            "impacted_systems": ["docs app"],
        }
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["change_summary"] == "Update help text"
    assert plan["risk_level"] == "low"
    assert plan["approvals"][2]["required"] is False
    assert plan["communication_plan"]["timing"] == "before and after change"
    assert "deployment or change ticket link" in plan["post_change_evidence"]


def test_change_management_plan_high_risk_production_change_escalates() -> None:
    plan = generate_change_management_plan(
        {
            "change_summary": "Rotate production database encryption key",
            "risk_level": "high",
            "environment": "production",
            "impacted_systems": "billing api; ledger database",
            "risk_owner": "GRC",
            "blackout_windows": ["month-end close"],
        }
    )

    assert plan["environment"] == "production"
    assert plan["impacted_systems"] == ["billing api", "ledger database"]
    assert plan["approvals"][2] == {
        "approval": "security_or_compliance",
        "owner": "GRC",
        "required": True,
    }
    assert plan["communication_plan"]["timing"] == "before, during, and after change window"
    assert plan["blackout_windows"] == ["month-end close"]
    assert any("incident commander" in step for step in plan["rollback"])
