from __future__ import annotations

from max.spec import generate_customer_migration_readiness_plan, render_customer_migration_readiness_plan_markdown


def test_customer_migration_readiness_plan_prioritizes_blocked_high_value_accounts() -> None:
    plan = generate_customer_migration_readiness_plan(
        {
            "customers": [
                {"customer": "ready-co", "owner": "csm", "comms_status": "sent", "success_criteria": ["login"], "value_tier": "standard"},
                {"customer": "blocked-co", "blockers": ["vpn allowlist"], "value_tier": "high"},
                {"customer": "risk-co", "owner": "csm", "comms_status": "missing", "value_tier": "high"},
            ],
            "migration_waves": [{"wave": "wave-unassigned", "date": "2026-06-01"}],
        }
    )

    assert plan["schema_version"] == "max-customer-migration-readiness-plan/v1"
    assert [row["customer"] for row in plan["customer_rows"]] == ["blocked-co", "risk-co", "ready-co"]
    assert [row["id"] for row in plan["customer_rows"]] == ["CMR-001", "CMR-002", "CMR-003"]
    assert plan["summary"] == {"customer_count": 3, "blocked_count": 1, "at_risk_count": 1, "ready_count": 1}
    assert any(gap["gap"] == "missing migration owner" for gap in plan["readiness_gaps"])
    assert any(gap["gap"] == "missing customer communications" for gap in plan["readiness_gaps"])
    assert any(gap["gap"] == "incomplete success criteria" for gap in plan["readiness_gaps"])
    assert plan["rollback_contacts"][0]["contact"] == "rollback-contact-required"


def test_customer_migration_readiness_markdown_sections_are_deterministic() -> None:
    payload = {"customers": [{"customer": "z", "blockers": ["x"]}, {"customer": "a", "blockers": ["x"]}]}

    first = render_customer_migration_readiness_plan_markdown(payload)
    second = render_customer_migration_readiness_plan_markdown(payload)

    assert first == second
    assert first.index("CMR-001: a") < first.index("CMR-002: z")
    for heading in ["## Customer Readiness", "## Readiness Gaps", "## Migration Waves", "## Rollback Contacts"]:
        assert heading in first
