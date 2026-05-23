from __future__ import annotations

from max.spec import generate_encryption_key_custody_transfer_plan


def test_encryption_key_custody_transfer_plan_covers_ceremony_and_monitoring() -> None:
    plan = generate_encryption_key_custody_transfer_plan(
        {
            "metadata": {
                "encryption_key_custody_transfer": {
                    "keys": [
                        {"key_id": "kms-prod-1", "environment": "prod", "current_custodian": "platform", "target_custodian": "security"},
                        {"key_id": "kms-stage-1", "environment": "stage"},
                    ],
                    "transfer_ceremony": ["dual control handoff"],
                    "access_approvals": ["security approval"],
                    "validation": ["decrypt canary"],
                    "audit_evidence": ["HSM audit log"],
                    "rollback": ["revoke target grants"],
                    "monitoring": ["key usage drift"],
                }
            }
        }
    )

    assert [row["name"] for row in plan["transfer_scope"]] == ["kms-prod-1", "kms-stage-1"]
    assert set(plan) >= {"custodians", "key_material_boundaries", "transfer_ceremony", "access_approvals", "validation", "audit_evidence", "rollback", "post_transfer_monitoring"}


def test_encryption_key_custody_transfer_plan_defaults_sparse_input() -> None:
    plan = generate_encryption_key_custody_transfer_plan({})

    assert plan["transfer_scope"][0]["name"] == "key custody transfer"
    assert plan["post_transfer_monitoring"][0]["owner"] == "security_owner"
