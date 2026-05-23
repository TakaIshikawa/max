"""Generate deterministic vendor access review exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.vendor_access_review_exception_plan.v1"
KIND = "max.spec.vendor_access_review_exception_plan"


def generate_vendor_access_review_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "vendor_access_review_exception")
    vendors = unique_records(
        named(hints.get("vendor_access_records") or hints.get("vendors") or hints.get("identities"), ("vendor", "identity", "system")),
        [{"name": "vendor access review exception", "owner": "vendor_owner", "severity": "high", "expiry": "30 days"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, vendor_access_record_count=len(vendors)),
        "vendor_access_records": [item("VAR", index, record, "vendor_owner", evidence_ids, "Review vendor access exception", name_keys=("name", "vendor", "identity", "system"), extra_keys=("vendor", "identity", "system", "role")) for index, record in enumerate(vendors, start=1)],
        "systems_accessed": section(hints, ("systems_accessed", "systems", "applications"), "VAS", "system_owner", "Confirm vendor system access", evidence_ids, ["systems and permission scope"], extra_keys=("system", "role")),
        "exception_rationale": section(hints, ("exception_rationale", "rationale", "justification"), "VAJ", "vendor_owner", "Document vendor access exception rationale", evidence_ids, ["time-boxed business need for delayed access review"]),
        "compensating_controls": section(hints, ("compensating_controls", "controls"), "VAC", "security_owner", "Operate compensating control", evidence_ids, ["least-privilege review, access logging, and owner attestation"]),
        "approver_review": section(hints, ("approvers", "approver_review", "approvals"), "VAA", "approval_owner", "Capture vendor access approval", evidence_ids, ["vendor owner, security, and procurement approval"]),
        "monitoring": section(hints, ("monitoring", "monitoring_controls"), "VAM", "security_owner", "Monitor vendor access exception", evidence_ids, ["daily access log review"]),
        "revocation_workflow": section(hints, ("revocation_workflow", "revocation", "expiry"), "VAX", "vendor_owner", "Revoke vendor access exception", evidence_ids, ["expiry check and access revocation workflow"]),
        "evidence_references": ctx["evidence_references"],
    }
