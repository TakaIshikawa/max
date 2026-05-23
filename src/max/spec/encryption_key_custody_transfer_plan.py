"""Generate deterministic encryption key custody transfer plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.encryption_key_custody_transfer_plan.v1"
KIND = "max.spec.encryption_key_custody_transfer_plan"


def generate_encryption_key_custody_transfer_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "encryption_key_custody_transfer")
    keys = unique_records(
        named(hints.get("keys") or hints.get("key_material") or hints.get("transfers"), ("key_id", "environment", "current_custodian", "target_custodian")),
        [{"name": "key custody transfer", "owner": "security_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, key_count=len(keys)),
        "transfer_scope": [
            item(
                "KCT",
                index,
                record,
                "security_owner",
                evidence_ids,
                "Transfer encryption key custody",
                name_keys=("name", "key_id", "environment", "current_custodian", "target_custodian"),
                extra_keys=("key_id", "environment", "current_custodian", "target_custodian"),
            )
            for index, record in enumerate(keys, start=1)
        ],
        "custodians": section(hints, ("custodians", "current_custodians", "target_custodians"), "KCU", "security_owner", "Confirm current and target custodian", evidence_ids, ["current custodian and target custodian"], extra_keys=("current_custodian", "target_custodian")),
        "key_material_boundaries": section(hints, ("boundaries", "key_material_boundaries", "material_boundaries"), "KCB", "security_owner", "Define key material boundary", evidence_ids, ["no plaintext export, HSM boundary, and wrapping key constraints"]),
        "transfer_ceremony": section(hints, ("ceremony", "transfer_ceremony", "steps"), "KCS", "security_owner", "Execute transfer ceremony step", evidence_ids, ["dual-control transfer ceremony with timestamped operator attestations"]),
        "access_approvals": section(hints, ("approvals", "access_approvals", "approvers"), "KCA", "approval_owner", "Capture access approval", evidence_ids, ["security, compliance, source custodian, and target custodian approval"]),
        "validation": section(hints, ("validation", "validations", "post_transfer_validation"), "KCV", "security_owner", "Validate transferred key", evidence_ids, ["decrypt/encrypt validation without exposing key material"]),
        "audit_evidence": section(hints, ("audit_evidence", "evidence", "audit"), "KCE", "compliance_owner", "Collect audit evidence", evidence_ids, ["ceremony transcript, access log, approval ticket, and HSM audit record"]),
        "rollback": section(hints, ("rollback", "rollback_plan", "backout"), "KCR", "security_owner", "Rollback custody transfer", evidence_ids, ["revoke target custody and restore source custodian access path"]),
        "post_transfer_monitoring": section(hints, ("monitoring", "post_transfer_monitoring", "monitors"), "KCM", "security_owner", "Monitor transferred key", evidence_ids, ["key usage, failed decrypts, grants, and custodian access drift"]),
        "evidence_references": ctx["evidence_references"],
    }
