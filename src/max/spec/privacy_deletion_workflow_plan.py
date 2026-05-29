"""Generate deterministic privacy deletion workflow plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary

SCHEMA_VERSION = "max.spec.privacy_deletion_workflow_plan.v1"
KIND = "max.spec.privacy_deletion_workflow_plan"


def generate_privacy_deletion_workflow_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "privacy_deletion_workflow")
    workflow = compact(hints.get("workflow") or hints.get("service")) or ctx["workflow_context"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, workflow=workflow),
        "data_inventory": section(hints, ("data_inventory", "data_types"), "PDW", "privacy_owner", "Inventory deletion data", evidence_ids, ["account identifiers, profile data, generated content, audit-linked records"]),
        "systems_of_record": section(hints, ("systems_of_record", "systems"), "PDS", "engineering_owner", "Map deletion system of record", evidence_ids, ["primary database, object storage, search index, analytics store"]),
        "deletion_triggers": section(hints, ("deletion_triggers", "triggers"), "PDT", "product_owner", "Define deletion trigger", evidence_ids, ["user request, admin action, retention expiry, processor callback"]),
        "processor_propagation": section(hints, ("processor_propagation", "processors"), "PDP", "vendor_owner", "Propagate deletion to processor", evidence_ids, ["notify processors and confirm deletion receipt"]),
        "verification_evidence": section(hints, ("verification_evidence", "verification"), "PDV", "qa_owner", "Verify deletion evidence", evidence_ids, ["tombstone, job log, processor confirmation, sampled absence check"]),
        "customer_notification": section(hints, ("customer_notification", "notifications"), "PDN", "support_owner", "Notify customer about deletion", evidence_ids, ["request received, completion notice, exception notice"]),
        "exception_handling": section(hints, ("exception_handling", "exceptions"), "PDE", "privacy_owner", "Handle deletion exception", evidence_ids, ["legal hold, fraud hold, processor delay, partial failure"]),
        "audit_retention": section(hints, ("audit_retention", "audit"), "PDA", "compliance_owner", "Retain deletion audit record", evidence_ids, ["minimal immutable audit record with retention period and access control"]),
        "signoff": section(hints, ("signoff", "owner_signoff"), "PDO", "program_owner", "Approve deletion workflow", evidence_ids, ["privacy, security, engineering, support signoff"]),
        "evidence_references": ctx["evidence_references"],
    }
