from __future__ import annotations

import json

from max.spec.api_quota_governance_plan import (
    SCHEMA_VERSION,
    generate_api_quota_governance_plan,
    render_api_quota_governance_plan_markdown,
)


def _spec() -> dict:
    return {
        "title": "Partner API Quotas",
        "api_consumers": [
            {"consumer": "mobile-app", "owner": "Mobile"},
            {"consumer": "analytics-sync", "owner": "Data"},
            {"consumer": "partner-portal", "owner": "Partners"},
        ],
        "current_limits": {
            "partner-portal": {"limit": 1000},
            "analytics-sync": {"limit": 5000},
            "mobile-app": {"limit": 2000},
        },
        "usage_peaks": {
            "analytics-sync": {"usage_peak": 2500},
            "mobile-app": {"usage_peak": 1800},
            "partner-portal": {"usage_peak": 1250},
        },
        "exception_requests": [
            {"consumer": "mobile-app", "requested_limit": 3000, "status": "pending", "justification": "Launch spike."},
            {"consumer": "partner-portal", "requested_limit": 1500, "status": "approved", "owner": "Partner Ops"},
        ],
        "enforcement_actions": {
            "over_quota": "Apply hard throttle until exception is approved.",
            "near_quota": "Send owner warning and review capacity.",
            "compliant": "Keep normal monitoring.",
        },
        "stakeholder_owners": {"mobile-app": "Mobile", "analytics-sync": "Data", "partner-portal": "Partners"},
        "monitoring_cadence": {"cadence": "daily", "metrics": ["utilization", "429s"], "review_owner": "API Platform"},
    }


def test_quota_governance_returns_deterministic_policy_rows() -> None:
    first = generate_api_quota_governance_plan(_spec())
    second = generate_api_quota_governance_plan(_spec())

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert first["kind"] == "max.api_quota_governance_plan"
    assert json.loads(json.dumps(first))["summary"]["title"] == "Partner API Quotas"
    assert [(row["consumer"], row["risk_state"]) for row in first["quota_policy_rows"]] == [
        ("partner-portal", "over_quota"),
        ("mobile-app", "near_quota"),
        ("analytics-sync", "compliant"),
    ]
    assert first["quota_policy_rows"][0]["limit"] == 1000.0
    assert first["quota_policy_rows"][0]["utilization"] == 1.25
    assert first["quota_policy_rows"][0]["owner"] == "Partners"
    assert first["quota_policy_rows"][0]["action"] == "Apply hard throttle until exception is approved."


def test_quota_governance_classifies_over_near_and_compliant_consumers() -> None:
    plan = generate_api_quota_governance_plan(_spec())

    by_consumer = {row["consumer"]: row for row in plan["quota_policy_rows"]}

    assert by_consumer["partner-portal"]["risk_state"] == "over_quota"
    assert by_consumer["mobile-app"]["risk_state"] == "near_quota"
    assert by_consumer["analytics-sync"]["risk_state"] == "compliant"
    assert plan["summary"]["over_quota_count"] == 1
    assert plan["summary"]["near_quota_count"] == 1
    assert plan["summary"]["compliant_count"] == 1


def test_quota_governance_markdown_contains_required_sections() -> None:
    plan = generate_api_quota_governance_plan(_spec())

    first = render_api_quota_governance_plan_markdown(plan)
    second = render_api_quota_governance_plan_markdown(plan)

    assert first == second
    assert first.startswith("# Partner API Quotas API Quota Governance Plan")
    assert "## Quota Summary" in first
    assert "### QPR1: partner-portal" in first
    assert "- Utilization: 125.0%" in first
    assert "## Exception Queue" in first
    assert "Launch spike." in first
    assert "## Enforcement Plan" in first
    assert "Apply hard throttle until exception is approved." in first
    assert "## Monitoring Cadence" in first
    assert "- Cadence: daily" in first
