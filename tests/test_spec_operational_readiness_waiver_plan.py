from __future__ import annotations

from max.spec.operational_readiness_waiver_plan import generate_operational_readiness_waiver_plan


def test_operational_readiness_waiver_plan_renders_temporary_waiver_with_controls() -> None:
    markdown = generate_operational_readiness_waiver_plan(
        {
            "project": {"title": "Checkout Launch"},
            "metadata": {
                "operational_readiness_waivers": [
                    {
                        "id": "ORW-7",
                        "reason": "load test final report is pending",
                        "severity": "medium",
                        "owner": "checkout_lead",
                        "approver": "release_director",
                        "expiry": "2026-06-10",
                        "unmet_criteria": ["load test sign-off"],
                        "compensating_controls": ["cap traffic at 10 percent", "watch checkout latency"],
                    }
                ]
            },
        }
    )

    assert markdown.startswith("# Checkout Launch Operational Readiness Waiver Plan")
    assert "## Waiver Summary" in markdown
    assert "## Unmet Criteria" in markdown
    assert "### ORW-7" in markdown
    assert "- Reason: load test final report is pending" in markdown
    assert "- ORW-7: cap traffic at 10 percent" in markdown
    assert "- ORW-7: approver=release_director; owner=checkout_lead; severity=medium." in markdown


def test_operational_readiness_waiver_plan_escalates_expired_waiver() -> None:
    markdown = generate_operational_readiness_waiver_plan(
        {
            "waivers": [
                {"id": "ACTIVE", "reason": "runbook polish", "severity": "low", "status": "active"},
                {
                    "id": "EXPIRED",
                    "reason": "missing rollback rehearsal",
                    "severity": "high",
                    "expired": True,
                    "unmet_criteria": ["rollback rehearsal"],
                },
            ]
        }
    )

    assert markdown.index("### EXPIRED") < markdown.index("### ACTIVE")
    assert "- Expired waivers: 1" in markdown
    assert "- EXPIRED: expiry=next readiness review; cadence=daily until closed; action=escalate immediately and block expansion." in markdown
    assert "approver=executive_sponsor" in markdown


def test_operational_readiness_waiver_plan_is_stable_and_defaults_missing_fields() -> None:
    payload = {
        "metadata": {
            "operational_readiness_waiver": {
                "waivers": [
                    {"id": "LOW", "reason": "dashboard label cleanup", "severity": "low"},
                    {"id": "HIGH", "reason": "pager routing incomplete", "severity": "critical"},
                ]
            }
        }
    }

    first = generate_operational_readiness_waiver_plan(payload)
    second = generate_operational_readiness_waiver_plan(payload)

    assert first == second
    assert first.index("### HIGH") < first.index("### LOW")
    assert "- Owner: readiness_owner" in first
    assert "expiry=next readiness review" in first
    assert "daily readiness owner review with documented go/no-go decision" in first
    assert "## Compensating Controls" in first
    assert "## Approval Requirements" in first
    assert "## Expiry Review" in first
    assert "## Closure Checklist" in first
