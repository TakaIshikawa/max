from __future__ import annotations

from max.spec import generate_service_account_lifecycle_plan, render_service_account_lifecycle_plan_markdown


def test_service_account_lifecycle_plan_classifies_risk_and_defaults_owner() -> None:
    plan = generate_service_account_lifecycle_plan(
        {
            "identity_platform_owner": "iam_team",
            "accounts": [
                {"account": "reporting-reader", "system": "warehouse", "owner": "data_team", "privileges": ["read"], "last_rotated": "2026-01-01", "last_used": "2026-02-01"},
                {"account": "billing-root", "system": "billing", "privileges": ["admin"], "last_rotated": "2025-01-01", "last_used": "never"},
            ],
        }
    )

    assert plan["schema_version"] == "max-service-account-lifecycle-plan/v1"
    assert plan["account_inventory"][0]["account"] == "billing-root"
    assert plan["account_inventory"][0]["id"] == "SAL-001"
    assert plan["account_inventory"][0]["owner"] == "iam_team"
    assert plan["account_inventory"][0]["risk"] == "critical"
    assert set(plan["account_inventory"][0]["risk_flags"]) == {"ownerless", "overprivileged", "rotation-overdue", "stale"}
    assert plan["summary"]["stale_count"] == 1
    assert plan["summary"]["ownerless_count"] == 1
    assert plan["rotation_actions"][0]["account_id"] == "SAL-001"


def test_service_account_lifecycle_markdown_sections_are_deterministic() -> None:
    payload = {"accounts": [{"account": "z-sa"}, {"account": "a-sa"}]}

    first = render_service_account_lifecycle_plan_markdown(payload)
    second = render_service_account_lifecycle_plan_markdown(payload)

    assert first == second
    for heading in ["## Inventory", "## Rotation Actions", "## Stale Accounts", "## Review Cadence"]:
        assert heading in first
    assert first.index("a-sa") < first.index("z-sa")
