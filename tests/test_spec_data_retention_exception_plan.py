from __future__ import annotations

from datetime import date, timedelta

from max.spec.data_retention_exception_plan import (
    generate_data_retention_exception_plan,
    render_data_retention_exception_plan_markdown,
)


def test_retention_exception_orders_expired_pending_and_approved_by_risk() -> None:
    expired = (date.today() - timedelta(days=1)).isoformat()
    soon = (date.today() + timedelta(days=10)).isoformat()
    later = (date.today() + timedelta(days=90)).isoformat()

    plan = generate_data_retention_exception_plan(
        {
            "project": {"title": "Retention Exceptions"},
            "exceptions": [
                {"request": "approved archive", "status": "approved", "expiry_date": later, "data_class": "contracts", "legal_basis": "customer contract"},
                {"request": "pending analytics", "status": "pending", "expiry_date": soon, "data_class": "usage", "legal_basis": "legitimate interest"},
                {"request": "expired export", "status": "approved", "expiry_date": expired, "data_class": "export", "legal_basis": "support case"},
            ],
        }
    )

    assert [row["request"] for row in plan["exception_inventory"]] == ["expired export", "pending analytics", "approved archive"]
    assert [row["expiry_risk"] for row in plan["exception_inventory"]] == ["expired", "expiring", "active"]
    assert plan["summary"]["pending_approval_count"] == 1
    assert plan["summary"]["expiry_risk_count"] == 2
    assert any("expired exceptions" in row["action"] for row in plan["review_actions"])


def test_retention_exception_defaults_pending_status() -> None:
    plan = generate_data_retention_exception_plan({"exceptions": [{"request": "hold logs"}]})

    assert plan["exception_inventory"][0]["approval_status"] == "pending"
    assert plan["pending_approvals"][0]["request"] == "hold logs"
    assert plan["compensating_controls"]


def test_retention_exception_markdown_contains_required_sections() -> None:
    soon = (date.today() + timedelta(days=10)).isoformat()
    plan = generate_data_retention_exception_plan(
        {
            "project": {"title": "Retention Exceptions"},
            "exceptions": [{"request": "pending analytics", "status": "pending", "expiry_date": soon, "approvers": ["legal"]}],
            "compensating_controls": ["restrict access to privacy team"],
            "evidence": {"rationale": "Customer contract requires temporary extension."},
        }
    )

    markdown = render_data_retention_exception_plan_markdown(plan)

    assert markdown.startswith("# Retention Exceptions Data Retention Exception Plan")
    assert "## Pending Approvals" in markdown
    assert "## Expiring Exceptions" in markdown
    assert "## Compensating Controls" in markdown
    assert "restrict access to privacy team" in markdown
    assert "## Audit Evidence" in markdown
    assert "Customer contract requires temporary extension." in markdown
