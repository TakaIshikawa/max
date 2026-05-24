"""Generate deterministic data minimization exception plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.data_minimization_exception_plan.v1"
KIND = "max.spec.data_minimization_exception_plan"


def generate_data_minimization_exception_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "data_minimization_exception")
    scope = unique_records(
        named(hints.get("exception_scope") or hints.get("scope") or hints.get("projects"), ("scope", "project", "dataset")),
        [{"name": "temporary expanded collection scope", "owner": "privacy_owner", "severity": "high"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, exception_scope_count=len(scope)),
        "exception_scope": [item("DME", index, record, "privacy_owner", evidence_ids, "Review data minimization exception scope", name_keys=("name", "scope", "project", "dataset"), extra_keys=("dataset", "system", "customer")) for index, record in enumerate(scope, start=1)],
        "justification": section(hints, ("justification", "rationale", "business_need"), "DMJ", "request_owner", "Document minimization exception justification", evidence_ids, ["specific business need and why minimized data is insufficient"]),
        "impacted_data_classes": section(hints, ("impacted_data_classes", "data_classes", "data_categories"), "DMD", "privacy_owner", "Classify impacted data", evidence_ids, ["data class, sensitivity, and collection delta"], extra_keys=("classification", "category")),
        "compensating_controls": section(hints, ("compensating_controls", "controls"), "DMC", "security_owner", "Operate compensating controls", evidence_ids, ["access limits, encryption, audit logging, and purpose binding"]),
        "expiry": section(hints, ("expiry", "expiration", "review_dates"), "DMX", "privacy_owner", "Track exception expiry", evidence_ids, ["expiry date and renewal gate"]),
        "approval": section(hints, ("approval", "approvals", "approvers"), "DMA", "approval_owner", "Capture exception approval", evidence_ids, ["privacy, security, legal, and product approval"]),
        "deletion_follow_up": section(hints, ("deletion_follow_up", "deletion", "cleanup"), "DMR", "privacy_owner", "Verify deletion follow-up", evidence_ids, ["post-expiry deletion and evidence capture"]),
        "evidence_references": ctx["evidence_references"],
    }
