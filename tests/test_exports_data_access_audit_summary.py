from __future__ import annotations

import json

from max.exports.data_access_audit_summary import (
    build_data_access_audit_summary_report,
    render_data_access_audit_summary_json,
    render_data_access_audit_summary_markdown,
)


def test_data_access_audit_summary_prioritizes_key_unresolved_findings() -> None:
    report = build_data_access_audit_summary_report(
        [
            {
                "system": "Warehouse",
                "dataset": "Revenue",
                "principal": "analyst@example.com",
                "owner": "data-governance",
                "finding_type": "stale_access",
                "risk": "medium",
                "status": "open",
                "last_seen": "2026-04-01",
                "evidence_links": ["https://evidence.example/stale"],
            },
            {
                "system": "CRM",
                "dataset": "Accounts",
                "principal": "ops-admin",
                "owner": "sales-ops",
                "finding_type": "excessive_privileges",
                "risk_level": "critical",
                "status": "open",
                "recommended_remediation": "remove admin role",
                "evidence": "https://evidence.example/admin",
            },
            {
                "system": "ERP",
                "dataset": "Invoices",
                "principal": "finance@example.com",
                "finding_type": "privileged_account",
                "status": "remediated",
            },
        ]
    )

    assert [finding["principal"] for finding in report["findings"]] == ["ops-admin", "analyst@example.com", "finance@example.com"]
    assert report["summary"]["open_count"] == 2
    assert report["summary"]["critical_high_count"] == 2
    assert report["summary"]["excessive_privileges_count"] == 1
    assert report["summary"]["stale_access_count"] == 1
    markdown = render_data_access_audit_summary_markdown(report)
    assert markdown.index("#### CRM - Accounts - ops-admin") < markdown.index("#### ERP - Invoices - finance@example.com")
    assert "- Recommended remediation: remove admin role" in markdown
    assert "- Evidence links: https://evidence.example/admin" in markdown
    assert "- Owner: sales-ops" in markdown


def test_data_access_audit_summary_groups_by_owner_and_normalizes_defaults() -> None:
    report = build_data_access_audit_summary_report(
        [
            {"system": "Warehouse", "dataset": "PII", "principal": "etl", "owner": "data", "finding": "exception"},
            {"system": "Warehouse", "dataset": "Logs", "principal": "viewer", "owner": "data", "finding_type": "other"},
        ],
        group_by="owner",
    )

    assert report["groups"][0]["name"] == "data"
    assert report["groups"][0]["finding_count"] == 2
    markdown = render_data_access_audit_summary_markdown(report)
    assert "Resolve or formally re-approve the exception" in markdown
    assert "Assign an owner, document access rationale" in markdown
    assert json.loads(render_data_access_audit_summary_json(report))["summary"]["unresolved_exception_count"] == 1


def test_data_access_audit_summary_renders_empty_state() -> None:
    report = build_data_access_audit_summary_report([])

    assert report["summary"]["finding_count"] == 0
    assert "No data access audit findings were supplied." in render_data_access_audit_summary_markdown(report)
