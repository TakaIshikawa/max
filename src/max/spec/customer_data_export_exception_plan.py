"""Generate deterministic customer data export exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.customer_data_export_exception_plan.v1"
KIND = "max.spec.customer_data_export_exception_plan"


def generate_customer_data_export_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_data_export_exception")
    scope = unique_records(
        named(hints.get("export_scope") or hints.get("exports") or hints.get("customers"), ("export", "customer", "account")),
        [{"name": "customer data export exception", "owner": "customer_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, export_scope_count=len(scope)),
        "export_scope": [item("CDE", index, record, "customer_owner", evidence_ids, "Review customer data export scope", name_keys=("name", "export", "customer", "account"), extra_keys=("customer", "account", "destination")) for index, record in enumerate(scope, start=1)],
        "customer_impact": section(hints, ("customer_impact", "customers", "accounts"), "CDC", "customer_owner", "Confirm customer export impact", evidence_ids, ["customer/account impact and authorization"]),
        "exception_rationale": section(hints, ("exception_rationale", "rationale", "justification"), "CDJ", "customer_owner", "Document customer data export exception rationale", evidence_ids, ["contractual, incident, support, or legal rationale"]),
        "data_classification": section(hints, ("data_classification", "data_categories", "categories"), "CDD", "privacy_owner", "Classify exported customer data", evidence_ids, ["data category and classification review"], extra_keys=("category", "classification")),
        "approval_workflow": section(hints, ("approval_workflow", "approvals", "approvers"), "CDA", "approval_owner", "Approve customer data export", evidence_ids, ["customer owner, privacy, security, and legal approval"]),
        "secure_transfer_controls": section(hints, ("secure_transfer_controls", "transfer_controls", "controls"), "CDT", "security_owner", "Operate secure transfer control", evidence_ids, ["encrypted transfer, recipient verification, access expiry, and transfer log"]),
        "retention_follow_up": section(hints, ("retention_follow_up", "retention", "deletion"), "CDR", "privacy_owner", "Follow up on export retention", evidence_ids, ["deletion confirmation and retention exception closure"]),
        "evidence_references": ctx["evidence_references"],
    }
