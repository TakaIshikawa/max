from __future__ import annotations

import json

from max.exports.support_entitlement_utilization import (
    build_support_entitlement_utilization_report,
    render_support_entitlement_utilization_json,
    render_support_entitlement_utilization_markdown,
)


def test_support_entitlement_utilization_prioritizes_actionable_accounts() -> None:
    report = build_support_entitlement_utilization_report(
        [
            {"account": "Gamma", "plan": "Standard", "used_units": 20, "allowance": 100},
            {"account": "Acme", "plan": "Enterprise", "used_units": 140, "allowance": 100, "owner": "cs", "recommended_action": "negotiate uplift"},
            {"account": "Beta", "plan": "Premium", "used_units": 15, "allowance": 100},
            {"account": "Delta", "plan": "Growth", "used_units": 85, "allowance": 100},
        ]
    )

    assert [row["account"] for row in report["entitlements"]] == ["Acme", "Delta", "Beta", "Gamma"]
    assert report["summary"]["overage_count"] == 1
    assert report["summary"]["nearing_limit_count"] == 1
    assert report["summary"]["underused_premium_count"] == 1
    markdown = render_support_entitlement_utilization_markdown(report)
    assert markdown.index("#### Acme") < markdown.index("#### Gamma")
    assert "- Plan: Enterprise" in markdown
    assert "- Used units: 140" in markdown
    assert "- Allowance: 100" in markdown
    assert "- Utilization: 140.0%" in markdown
    assert "- Recommended action: negotiate uplift" in markdown


def test_support_entitlement_utilization_groups_and_normalizes_defaults() -> None:
    report = build_support_entitlement_utilization_report(
        [
            {"account": "Acme", "plan": "Enterprise", "used_units": 5, "allowance": 100},
            {"account": "Beta", "plan": "Enterprise", "used_units": 50, "allowance": 100},
        ],
        group_by="plan",
    )

    assert report["groups"][0]["name"] == "Enterprise"
    assert report["groups"][0]["account_count"] == 2
    markdown = render_support_entitlement_utilization_markdown(report)
    assert "Review premium plan fit and activate unused support motions." in markdown
    assert json.loads(render_support_entitlement_utilization_json(report))["summary"]["account_count"] == 2


def test_support_entitlement_utilization_renders_empty_state() -> None:
    report = build_support_entitlement_utilization_report([])

    assert report["summary"]["average_utilization_percent"] == 0.0
    assert "No support entitlement utilization records were supplied." in render_support_entitlement_utilization_markdown(report)
