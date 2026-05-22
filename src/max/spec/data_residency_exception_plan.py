"""Generate deterministic data residency exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.data_residency_exception_plan.v1"
KIND = "max.spec.data_residency_exception_plan"


def generate_data_residency_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_residency_exception")
    exceptions = unique_records(
        named(hints.get("exceptions") or hints.get("requested_exception"), ("request", "region", "data_class")),
        [{"name": "temporary data residency exception", "owner": "privacy_owner", "severity": "medium", "expiry": "not recorded"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_count=len(exceptions)),
        "exception_scope": [
            item("DRE", index, record, "privacy_owner", evidence_ids, "Review data residency exception", name_keys=("name", "request", "region", "data_class"), extra_keys=("region", "data_class", "customer"))
            for index, record in enumerate(exceptions, start=1)
        ],
        "affected_regions": section(hints, ("regions", "affected_regions"), "DRR", "data_owner", "Confirm affected region", evidence_ids, ["origin and destination residency region"], extra_keys=("region",)),
        "customer_data_classes": section(hints, ("customers", "data_classes", "customer_data_classes"), "DRD", "privacy_owner", "Classify customer and data scope", evidence_ids, ["customer cohort and regulated data class"], extra_keys=("customer", "data_class")),
        "compensating_controls": section(hints, ("compensating_controls", "controls"), "DRC", "security_owner", "Operate compensating control", evidence_ids, ["encryption, access logging, and transfer minimization"]),
        "approval_gates": section(hints, ("approvers", "approvals"), "DRA", "approval_owner", "Capture residency exception approval", evidence_ids, ["privacy, legal, security, and customer approver"]),
        "monitoring": section(hints, ("monitoring", "monitors"), "DRM", "compliance_owner", "Monitor residency exception", evidence_ids, ["residency transfer monitoring and customer impact review"]),
        "expiration_reviews": section(hints, ("expiry", "expiration", "expiration_reviews"), "DRX", "privacy_owner", "Review exception expiration", evidence_ids, ["time-boxed exception expiry date"]),
        "rollback_remediation": section(hints, ("rollback", "remediation", "rollback_remediation"), "DRB", "engineering_owner", "Rollback or remediate residency exception", evidence_ids, ["restore regional processing and purge temporary copies"]),
        "evidence_references": ctx["evidence_references"],
    }
