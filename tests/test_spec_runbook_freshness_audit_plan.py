from __future__ import annotations

from max.spec import generate_runbook_freshness_audit_plan, render_runbook_freshness_audit_plan_markdown


def test_runbook_freshness_audit_plan_calculates_overdue_from_anchor() -> None:
    plan = generate_runbook_freshness_audit_plan(
        {
            "audit_cadence": {"cadence_days": 90, "anchor_date": "2026-05-01"},
            "runbooks": [
                {"runbook": "checkout restore", "owner": "sre", "last_reviewed": "2026-04-15", "service_criticality": "critical"},
                {"runbook": "billing failover", "last_reviewed": "2025-12-01", "service_criticality": "critical", "incident_references": ["INC-1"]},
            ],
        }
    )

    assert plan["schema_version"] == "max-runbook-freshness-audit-plan/v1"
    assert plan["runbook_rows"][0]["runbook"] == "billing failover"
    assert plan["runbook_rows"][0]["id"] == "RFA-001"
    assert plan["runbook_rows"][0]["owner"] == "runbook_owner"
    assert plan["summary"]["overdue_count"] == 1
    assert plan["summary"]["critical_overdue_count"] == 1
    assert plan["update_actions"][0]["runbook_id"] == "RFA-001"


def test_runbook_freshness_audit_markdown_sections_are_deterministic() -> None:
    payload = {"runbooks": [{"runbook": "z", "last_reviewed": "2025-01-01"}, {"runbook": "a", "last_reviewed": "2025-01-01"}]}

    first = render_runbook_freshness_audit_plan_markdown(payload)
    second = render_runbook_freshness_audit_plan_markdown(payload)

    assert first == second
    assert first.index("RFA-001: a") < first.index("RFA-002: z")
    for heading in ["## Runbook Inventory", "## Overdue Reviews", "## Update Actions", "## Audit Cadence"]:
        assert heading in first
