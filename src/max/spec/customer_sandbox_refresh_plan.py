"""Generate deterministic customer sandbox refresh plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.customer_sandbox_refresh_plan.v1"
KIND = "max.spec.customer_sandbox_refresh_plan"


def generate_customer_sandbox_refresh_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_sandbox_refresh")
    tenants = unique_records(
        named(hints.get("tenants") or hints.get("tenant_scope"), ("tenant", "customer", "environment")),
        [{"name": "customer sandbox tenant", "owner": "customer_success_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, tenant_count=len(tenants)),
        "refresh_scope": [
            item("CSR", index, record, "customer_success_owner", evidence_ids, "Review sandbox refresh scope", name_keys=("name", "tenant", "customer", "environment"), extra_keys=("tenant", "customer", "environment"))
            for index, record in enumerate(tenants, start=1)
        ],
        "source_snapshot": section(hints, ("source_snapshot", "snapshots"), "CSS", "data_owner", "Prepare source snapshot", evidence_ids, ["approved production-like source snapshot"]),
        "masking_requirements": section(hints, ("masking", "masking_requirements", "privacy_controls"), "CSM", "privacy_owner", "Apply masking requirement", evidence_ids, ["PII masking and tokenization policy"]),
        "timing_window": section(hints, ("window", "downtime", "timing_window"), "CST", "release_manager", "Coordinate refresh timing", evidence_ids, ["refresh window and downtime notice"]),
        "validation_checks": section(hints, ("validation", "validation_checks"), "CSV", "qa_owner", "Validate refreshed sandbox", evidence_ids, ["login, data shape, integration, and masking validation"]),
        "stakeholder_notifications": section(hints, ("notifications", "stakeholder_notifications"), "CSN", "customer_success_owner", "Notify stakeholders", evidence_ids, ["customer and internal refresh notice"]),
        "rollback": section(hints, ("rollback", "rollback_steps"), "CSB", "engineering_owner", "Rollback sandbox refresh", evidence_ids, ["restore prior sandbox snapshot"]),
        "cleanup": section(hints, ("cleanup", "cleanup_steps"), "CSC", "data_owner", "Clean up refresh artifacts", evidence_ids, ["purge temporary exports and refresh credentials"]),
        "evidence_references": ctx["evidence_references"],
    }
