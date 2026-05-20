from __future__ import annotations

import json

from max.exports.soc2_control_evidence_gap import (
    build_soc2_control_evidence_gap_report,
    render_soc2_control_evidence_gap_json,
    render_soc2_control_evidence_gap_markdown,
)


def test_soc2_gap_report_orders_highest_risk_missing_gaps_first() -> None:
    report = build_soc2_control_evidence_gap_report([
        {
            "control_id": "CC7.2",
            "control_name": "Incident monitoring",
            "domain": "Security Operations",
            "owner": "secops",
            "evidence": "alert review sample",
            "evidence_status": "stale",
            "risk_level": "high",
            "due_date": "2026-06-15",
        },
        {
            "control_id": "CC6.1",
            "control_name": "Logical access",
            "domain": "Access Control",
            "owner": "iam",
            "evidence": "quarterly access review",
            "evidence_status": "missing",
            "risk_level": "critical",
            "due_date": "2026-06-01",
            "remediation": "complete privileged access review",
        },
        {
            "control_id": "CC2.1",
            "domain": "Governance",
            "evidence": "board minutes",
            "evidence_status": "approved",
            "risk_level": "low",
        },
    ])

    assert [gap["control_id"] for gap in report["gaps"]] == ["CC6.1", "CC7.2"]
    assert report["summary"]["control_count"] == 2
    assert report["summary"]["critical_high_count"] == 2
    markdown = render_soc2_control_evidence_gap_markdown(report)
    assert markdown.index("#### CC6.1 - Logical access") < markdown.index("#### CC7.2 - Incident monitoring")
    assert "- Missing evidence: 1" in markdown
    assert "- Stale evidence: 1" in markdown
    assert "- Remediation: complete privileged access review" in markdown


def test_soc2_gap_report_groups_by_owner_and_merges_duplicates() -> None:
    report = build_soc2_control_evidence_gap_report(
        [
            {
                "control_id": "CC3.2",
                "control_name": "Risk assessment",
                "domain": "Risk Management",
                "owner": "grc",
                "evidence": ["risk register", "risk committee notes"],
                "status": "rejected",
                "risk": "medium",
                "due_date": "2026-07-15",
            },
            {
                "control_id": "CC3.2",
                "control_name": "Risk assessment",
                "domain": "Risk Management",
                "owner": "grc",
                "evidence": ["risk committee notes", "risk register"],
                "status": "missing",
                "risk": "high",
                "due_date": "2026-07-01",
            },
        ],
        group_by="owner",
    )

    assert report["summary"]["gap_count"] == 1
    assert report["groups"][0]["name"] == "grc"
    assert report["gaps"][0]["evidence_status"] == "missing"
    assert report["gaps"][0]["risk_level"] == "high"
    assert report["gaps"][0]["due_date"] == "2026-07-01"
    assert "- Evidence: risk committee notes, risk register" in render_soc2_control_evidence_gap_markdown(report)


def test_soc2_gap_report_renders_empty_guidance_and_json() -> None:
    report = build_soc2_control_evidence_gap_report([])

    assert report["summary"]["gap_count"] == 0
    markdown = render_soc2_control_evidence_gap_markdown(report)
    assert "No SOC 2 evidence gaps were supplied." in markdown
    assert "Confirm each SOC 2 control has a named owner" in markdown
    assert json.loads(render_soc2_control_evidence_gap_json(report))["groups"] == []
