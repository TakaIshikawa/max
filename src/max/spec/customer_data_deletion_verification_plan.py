"""Generate deterministic customer data deletion verification plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.customer_data_deletion_verification_plan.v1"
KIND = "max.spec.customer_data_deletion_verification_plan"


def generate_customer_data_deletion_verification_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_data_deletion_verification")
    scope = unique_records(
        named(hints.get("deletion_scope") or hints.get("customers") or hints.get("accounts"), ("customer", "account", "tenant")),
        [{"name": "customer deletion request", "owner": "support_owner", "severity": "high"}],
    )
    systems = section(hints, ("systems", "stores", "affected_systems"), "CDS", "system_owner", "Verify deletion in system", evidence_ids, ["primary stores and derived data stores"])
    backup_defaults = [{"name": "backup deletion or expiry verification", "owner": "privacy_owner", "severity": "medium"}]
    downstream_defaults = [{"name": "downstream publisher deletion verification", "owner": "publisher_owner", "severity": "medium"}]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, deletion_scope_count=len(scope), system_count=len(systems)),
        "deletion_scope": [item("CDD", index, record, "support_owner", evidence_ids, "Confirm deletion scope", name_keys=("name", "customer", "account", "tenant"), extra_keys=("customer", "account", "request_id")) for index, record in enumerate(scope, start=1)],
        "affected_systems": systems,
        "backup_verification": section(hints, ("backups", "backup_verification"), "CDB", "privacy_owner", "Verify backup retention handling", evidence_ids, backup_defaults),
        "downstream_destinations": section(hints, ("downstream_destinations", "publishers", "destinations"), "CDP", "publisher_owner", "Verify downstream deletion", evidence_ids, downstream_defaults),
        "verification_evidence": section(hints, ("verification_evidence", "evidence", "artifacts"), "CDE", "privacy_owner", "Capture deletion evidence", evidence_ids, ["deletion logs, store queries, backup policy proof, and publisher confirmations"]),
        "exceptions": section(hints, ("exceptions", "residual_retention", "holds"), "CDX", "privacy_owner", "Review deletion exception", evidence_ids, ["legal hold or residual retention exception"]),
        "customer_communication": section(hints, ("customer_communication", "communication"), "CDC", "support_owner", "Notify customer", evidence_ids, ["customer deletion completion message and support owner checkpoint"]),
        "residual_retention_signoff": section(hints, ("residual_retention_signoff", "signoff", "approvals"), "CDR", "privacy_owner", "Sign off residual retention", evidence_ids, ["privacy and support owner signoff"]),
        "evidence_references": ctx["evidence_references"],
    }
