from __future__ import annotations

from max.spec.change_freeze_exception_plan import generate_change_freeze_exception_plan


def test_change_freeze_exception_plan_renders_approved_exception() -> None:
    markdown = generate_change_freeze_exception_plan(
        {
            "project": {"title": "Payments Release"},
            "metadata": {
                "change_freeze_exceptions": [
                    {
                        "id": "PAY-7",
                        "title": "payment provider certificate update",
                        "status": "approved",
                        "risk": "medium",
                        "blast_radius": "production payment service",
                        "owner": "payments_oncall",
                        "approver": "release_director",
                        "expiry": "2026-06-01",
                    }
                ]
            },
        }
    )

    assert markdown.startswith("# Payments Release Change Freeze Exception Plan")
    assert "## Request Inventory" in markdown
    assert "### PAY-7: payment provider certificate update" in markdown
    assert "- Status: approved" in markdown
    assert "- Owner: payments_oncall" in markdown
    assert "approver=release_director" in markdown


def test_change_freeze_exception_plan_prioritizes_rejected_high_risk_exception() -> None:
    markdown = generate_change_freeze_exception_plan(
        {
            "metadata": {
                "change_freeze_exception": {
                    "requests": [
                        {"id": "LOW", "title": "copy update", "status": "approved", "risk": "low", "blast_radius": "internal"},
                        {
                            "id": "HIGH",
                            "title": "database failover",
                            "status": "rejected",
                            "risk": "critical",
                            "blast_radius": "all customers",
                            "control": "freeze until failover rehearsal is approved",
                        },
                    ]
                }
            }
        }
    )

    assert markdown.index("### HIGH: database failover") < markdown.index("### LOW: copy update")
    assert "Reject or escalate before thaw; approver=change_advisory_board; owner=release_manager." in markdown
    assert "freeze until failover rehearsal is approved" in markdown


def test_change_freeze_exception_plan_is_stable_and_defaults_missing_fields() -> None:
    payload = {
        "requests": [
            {"id": "B", "title": "team tooling", "risk": "medium", "blast_radius": "team"},
            {"id": "A", "title": "customer hotfix", "risk": "high", "blast_radius": "customer"},
        ]
    }

    first = generate_change_freeze_exception_plan(payload)
    second = generate_change_freeze_exception_plan(payload)

    assert first == second
    assert first.index("### A: customer hotfix") < first.index("### B: team tooling")
    assert "- Owner: release_manager" in first
    assert "- Approver: change_advisory_board" in first
    assert "- Expiry: next freeze review" in first
    assert "## Risk Controls" in first
    assert "## Approval Path" in first
    assert "## Rollback Expectations" in first
    assert "## Audit Trail" in first
