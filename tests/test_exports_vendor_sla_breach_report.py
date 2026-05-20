from __future__ import annotations

import json

from max.exports.vendor_sla_breach_report import (
    build_vendor_sla_breach_report,
    render_vendor_sla_breach_json,
    render_vendor_sla_breach_markdown,
)


def test_vendor_sla_breach_report_prioritizes_active_severe_breaches() -> None:
    report = build_vendor_sla_breach_report(
        [
            {
                "vendor": "Nimbus",
                "service": "Email relay",
                "metric": "99.9% uptime",
                "duration": "20 minutes",
                "impact": "Delayed notifications",
                "severity": "medium",
                "status": "resolved",
                "owner": "platform",
                "next_action": "review credit memo",
            },
            {
                "vendor": "Acme Cloud",
                "service": "Database",
                "breached_metric": "p95 latency under 200ms",
                "duration": "3 hours",
                "impact": "Checkout latency for enterprise tenants",
                "severity": "critical",
                "status": "active",
                "owner": "vendor-management",
                "next_action": "escalate to TAM",
                "detected_at": "2026-05-18",
            },
            {
                "vendor": "Beta CDN",
                "service": "Static assets",
                "metric": "99.95% availability",
                "duration": "45 minutes",
                "severity": "low",
                "status": "active",
            },
        ]
    )

    assert [breach["vendor"] for breach in report["breaches"]] == ["Acme Cloud", "Beta CDN", "Nimbus"]
    assert report["summary"]["active_count"] == 2
    assert report["summary"]["critical_high_count"] == 1
    markdown = render_vendor_sla_breach_markdown(report)
    assert markdown.index("#### Acme Cloud - Database") < markdown.index("#### Nimbus - Email relay")
    assert "- Breached metric: p95 latency under 200ms" in markdown
    assert "- Duration: 3 hours" in markdown
    assert "- Impact: Checkout latency for enterprise tenants" in markdown
    assert "- Owner: vendor-management" in markdown
    assert "- Next action: escalate to TAM" in markdown


def test_vendor_sla_breach_report_groups_and_normalizes_missing_values() -> None:
    report = build_vendor_sla_breach_report(
        [
            {"vendor": "Acme Cloud", "service": "Database", "severity": "high", "status": "active"},
            {"vendor": "Acme Cloud", "service": "Queue", "severity": "low", "status": "resolved"},
        ],
        group_by="vendor",
    )

    assert report["groups"][0]["name"] == "Acme Cloud"
    assert report["groups"][0]["breach_count"] == 2
    markdown = render_vendor_sla_breach_markdown(report)
    assert "Unspecified metric" in markdown
    assert "Confirm owner, remediation ETA, and customer impact." in markdown
    assert json.loads(render_vendor_sla_breach_json(report))["summary"]["vendor_count"] == 1


def test_vendor_sla_breach_report_renders_empty_state() -> None:
    report = build_vendor_sla_breach_report([])

    assert report["summary"]["breach_count"] == 0
    assert "No vendor SLA breaches were supplied." in render_vendor_sla_breach_markdown(report)
