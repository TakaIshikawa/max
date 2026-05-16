from __future__ import annotations

from max.spec.backup_restore_test_plan import (
    KIND,
    SCHEMA_VERSION,
    generate_backup_restore_test_plan,
)


def test_backup_restore_test_plan_standard_restore() -> None:
    plan = generate_backup_restore_test_plan(
        {"system": "Analytics API", "backup_scope": ["postgres", "s3 exports"]}
    )

    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == KIND
    assert plan["system"] == "Analytics API"
    assert plan["backup_scope"] == ["postgres", "s3 exports"]
    assert plan["recovery_objectives"] == {"rpo": "24 hours", "rto": "8 hours"}
    assert plan["test_cadence"] == "quarterly"
    assert any("checksums" in check for check in plan["validation_checks"])
    assert "backup identifier and restore start/end timestamps" in plan["evidence_capture"]


def test_backup_restore_test_plan_critical_system_tightens_objectives() -> None:
    plan = generate_backup_restore_test_plan(
        {
            "system_name": "Billing Ledger",
            "criticality": "critical",
            "data_stores": "postgres; ledger snapshots",
            "service_owner": "Payments",
        }
    )

    assert plan["recovery_objectives"] == {"rpo": "15 minutes", "rto": "1 hour"}
    assert plan["test_cadence"] == "monthly"
    assert plan["owners"]["service_owner"] == "Payments"
    assert any("transaction replay" in check for check in plan["validation_checks"])
    assert "Recovery exceeds RTO target." in plan["rollback_criteria"]
