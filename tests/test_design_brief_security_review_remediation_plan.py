from __future__ import annotations

import json

import pytest

from max.analysis.design_brief_security_review_remediation_plan import (
    KIND,
    build_design_brief_security_review_remediation_plan,
    render_design_brief_security_review_remediation_plan,
    security_review_remediation_plan_filename,
)


def test_security_review_remediation_plan_builds_prioritized_rows() -> None:
    report = build_design_brief_security_review_remediation_plan(_brief())

    assert report == build_design_brief_security_review_remediation_plan(_brief())
    assert json.loads(json.dumps(report)) == report
    assert report["kind"] == KIND
    assert [row["id"] for row in report["remediation_actions"]] == ["F2", "F1", "F3"]
    assert report["remediation_actions"][0] == {
        "id": "F2",
        "finding": "OAuth scopes too broad",
        "severity": "critical",
        "owner": "Security lead",
        "due_window": "0-3 days",
        "evidence_refs": ["sig-auth"],
        "status": "open",
        "resolved": False,
        "action": "Restrict OAuth scopes",
        "approval_owner": "CISO delegate",
    }
    assert report["summary"]["blocking_finding_count"] == 1
    assert report["summary"]["evidence_gap_count"] == 0
    assert report["actions_by_severity"][0]["severity"] == "critical"
    assert report["actions_by_owner"][0]["owner"] == "Engineering lead"
    assert report["recommendation"]["status"] == "blocked_pending_security_remediation"


def test_security_review_remediation_plan_sparse_findings_flag_evidence_gaps() -> None:
    report = build_design_brief_security_review_remediation_plan(
        {"id": "dbf-security-sparse", "security_findings": [{}]}
    )

    row = report["remediation_actions"][0]
    assert row["finding"] == "Security finding 1"
    assert row["severity"] == "unknown"
    assert row["owner"] == "Security owner"
    assert row["due_window"] == "triage required"
    assert row["status"] == "open"
    assert [gap["id"] for gap in report["unresolved_evidence_gaps"]] == ["SRR1_missing_evidence"]
    assert report["summary"]["readiness_status"] == "blocked_pending_security_remediation"


def test_security_review_remediation_plan_ordering_is_stable() -> None:
    report = build_design_brief_security_review_remediation_plan(
        {
            "id": "dbf-ordering",
            "security_findings": [
                {"id": "low", "finding": "Low issue", "severity": "low", "owner": "B", "evidence_refs": ["e2"]},
                {"id": "high-b", "finding": "High B issue", "severity": "high", "owner": "B", "evidence_refs": ["e1"]},
                {"id": "high-a", "finding": "High A issue", "severity": "high", "owner": "A", "evidence_refs": ["e3"]},
            ],
        }
    )

    assert [row["id"] for row in report["remediation_actions"]] == ["high-a", "high-b", "low"]


def test_security_review_remediation_plan_renderers_and_filename() -> None:
    report = build_design_brief_security_review_remediation_plan(_brief())

    assert json.loads(render_design_brief_security_review_remediation_plan(report, "json")) == report
    markdown = render_design_brief_security_review_remediation_plan(report, "markdown")
    assert markdown.startswith("# Security Review Remediation Plan: Security Remediation Brief")
    assert "## Readiness Summary" in markdown
    assert "## Prioritized Remediation Actions" in markdown
    assert "## Unresolved Evidence Gaps" in markdown
    assert "## Approval Owners" in markdown
    assert (
        security_review_remediation_plan_filename(_brief())
        == "dbf-security-1-Security-Remediation-Brief-security-review-remediation-plan.md"
    )
    assert security_review_remediation_plan_filename(_brief(), "json").endswith(".json")
    with pytest.raises(ValueError, match="Unsupported security review remediation plan format"):
        render_design_brief_security_review_remediation_plan(report, "yaml")


def _brief() -> dict:
    return {
        "id": "dbf-security-1",
        "title": "Security Remediation Brief",
        "source_idea_ids": ["idea-security-1"],
        "security_findings": [
            {
                "id": "F1",
                "finding": "Audit logs missing",
                "severity": "medium",
                "owner": "Engineering lead",
                "due_window": "2 weeks",
                "evidence_refs": ["sig-audit"],
                "status": "in progress",
                "action": "Add audit events",
            },
            {
                "id": "F2",
                "finding": "OAuth scopes too broad",
                "severity": "critical",
                "owner": "Security lead",
                "evidence_refs": ["sig-auth", "sig-auth"],
                "action": "Restrict OAuth scopes",
                "approval_owner": "CISO delegate",
            },
            {
                "id": "F3",
                "finding": "Fixture redaction verified",
                "severity": "low",
                "owner": "QA lead",
                "evidence_refs": ["test-redaction"],
                "status": "resolved",
            },
        ],
        "approval_owners": ["CISO delegate"],
    }
