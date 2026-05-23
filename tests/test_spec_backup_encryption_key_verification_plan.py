from __future__ import annotations

import json

from max.spec import generate_backup_encryption_key_verification_plan


def test_backup_encryption_key_verification_plan_covers_verification_workflow() -> None:
    plan = generate_backup_encryption_key_verification_plan(
        {
            "metadata": {
                "backup_encryption_key_verification": {
                    "keys": [
                        {"key_id": "backup-kms-prod", "backup_set": "prod-db", "environment": "prod"},
                        {"key_id": "backup-kms-stage", "backup_set": "stage-db"},
                    ],
                    "restore_validation": ["restore prod-db snapshot and validate decrypt"],
                    "evidence_capture": ["KMS decrypt audit event"],
                    "owner_approvals": ["security owner approval"],
                    "exceptions": ["failed restore opens incident ticket"],
                    "next_verification_date": [{"name": "2026-06-30", "next_verification_date": "2026-06-30"}],
                }
            },
            "evidence": {"insight_ids": ["backup-key-1"]},
        }
    )

    assert plan["kind"] == "max.spec.backup_encryption_key_verification_plan"
    assert [row["name"] for row in plan["verification_scope"]] == ["backup-kms-prod", "backup-kms-stage"]
    assert set(plan) >= {"key_inventory", "restore_validation", "evidence_capture", "owner_approvals", "exception_handling", "follow_up"}
    assert json.loads(json.dumps(plan)) == plan


def test_backup_encryption_key_verification_plan_defaults_sparse_input() -> None:
    plan = generate_backup_encryption_key_verification_plan({})

    assert plan["verification_scope"][0]["name"] == "backup encryption key inventory"
    assert plan["restore_validation"][0]["owner"] == "recovery_owner"
    assert plan["follow_up"][0]["name"] == "next verification date required and tracked before evidence expiry"
