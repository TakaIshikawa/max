from __future__ import annotations

from max.spec import (
    generate_audit_finding_remediation_plan,
    render_audit_finding_remediation_plan_markdown,
)


def test_audit_finding_remediation_plan_sorts_and_defaults() -> None:
    plan = generate_audit_finding_remediation_plan(
        {
            "findings": [
                {"finding": "logging evidence gap", "severity": "medium", "due_date": "2026-06-10", "status": "open"},
                {
                    "finding": "privileged access exception",
                    "severity": "critical",
                    "owner": "iam_owner",
                    "due_date": "2026-05-30",
                    "status": "blocked",
                    "control": "AC-2",
                    "framework": "SOC 2",
                    "action": "remove stale admin grants",
                },
                {"finding": "backup restore evidence", "severity": "high", "due_date": "2026-05-20"},
            ]
        }
    )

    assert plan["schema_version"] == "max-audit-finding-remediation-plan/v1"
    assert plan["kind"] == "max.spec.audit_finding_remediation_plan"
    assert [row["id"] for row in plan["remediation_rows"]] == ["AFR-001", "AFR-002", "AFR-003"]
    assert [row["finding"] for row in plan["remediation_rows"]] == [
        "privileged access exception",
        "backup restore evidence",
        "logging evidence gap",
    ]
    assert plan["summary"]["severity_counts"] == {"critical": 1, "high": 1, "medium": 1}
    assert plan["summary"]["status_counts"] == {"blocked": 1, "open": 2}
    assert plan["remediation_rows"][1]["owner"] == "audit_remediation_owner"
    assert plan["remediation_rows"][1]["action"] == "define corrective action and evidence owner"
    assert plan["escalation_items"][0]["finding_id"] == "AFR-001"
    assert plan["review_cadence"]["cadence"] == "weekly"


def test_audit_finding_remediation_plan_markdown_is_deterministic() -> None:
    payload = {
        "metadata": {
            "audit_findings": [
                {"name": "z finding", "severity": "low", "due": "2026-08-01"},
                {"name": "a finding", "severity": "low", "due": "2026-08-01"},
            ],
            "review_cadence": {"cadence": "monthly", "reviewer": "grc_lead"},
        }
    }

    first = render_audit_finding_remediation_plan_markdown(payload)
    second = render_audit_finding_remediation_plan_markdown(payload)

    assert first == second
    assert first.index("### AFR-001: a finding") < first.index("### AFR-002: z finding")
    for heading in ["## Findings", "## Remediation Actions", "## Escalations", "## Review Cadence"]:
        assert heading in first
    assert "- No escalations required." in first
    assert "- Reviewer: grc_lead" in first
