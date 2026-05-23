"""Generate deterministic backup encryption key verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.backup_encryption_key_verification_plan.v1"
KIND = "max.spec.backup_encryption_key_verification_plan"


def generate_backup_encryption_key_verification_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "backup_encryption_key_verification")
    keys = unique_records(
        named(
            hints.get("keys") or hints.get("key_inventory") or hints.get("backup_keys"),
            ("key_id", "backup_set", "environment", "owner"),
        ),
        [{"name": "backup encryption key inventory", "owner": "security_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, key_count=len(keys)),
        "verification_scope": [
            item(
                "BKV",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Verify backup encryption key",
                name_keys=("name", "key_id", "backup_set", "environment", "owner"),
                extra_keys=("key_id", "backup_set", "environment", "algorithm", "custodian"),
            )
            for index, record in enumerate(keys, start=1)
        ],
        "key_inventory": section(hints, ("inventory", "key_inventory", "keys"), "BKI", "security_owner", "Confirm backup key inventory", evidence_ids, ["active backup encryption keys, aliases, custodians, and protected backup sets"], extra_keys=("key_id", "backup_set", "environment", "custodian")),
        "restore_validation": section(hints, ("restore_validation", "restores", "validation"), "BKR", "recovery_owner", "Validate encrypted backup restore", evidence_ids, ["restore representative backup and verify decrypt path without exposing key material"]),
        "evidence_capture": section(hints, ("evidence", "evidence_capture", "audit_evidence"), "BKE", "compliance_owner", "Capture verification evidence", evidence_ids, ["restore transcript, KMS or HSM audit event, checksum, and operator attestation"]),
        "owner_approvals": section(hints, ("approvals", "owner_approvals", "approvers"), "BKA", "approval_owner", "Capture owner approval", evidence_ids, ["security owner, backup owner, recovery owner, and compliance approval"]),
        "exception_handling": section(hints, ("exceptions", "exception_handling", "exception_process"), "BKX", "security_owner", "Handle verification exception", evidence_ids, ["document failed restore, missing custody, stale key, or evidence gap with remediation owner"]),
        "follow_up": section(hints, ("follow_up", "next_verification", "next_verification_date"), "BKF", "security_owner", "Schedule next verification", evidence_ids, ["next verification date required and tracked before evidence expiry"], extra_keys=("next_verification_date", "deadline")),
        "evidence_references": ctx["evidence_references"],
    }
