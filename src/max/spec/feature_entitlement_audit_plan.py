"""Generate deterministic feature entitlement audit plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._review_plan_common import base, source_summary, unique_records


SCHEMA_VERSION = "max.spec.feature_entitlement_audit_plan.v1"
KIND = "max.spec.feature_entitlement_audit_plan"


def generate_feature_entitlement_audit_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "feature_entitlement_audit")
    findings = unique_records(
        named(hints.get("findings") or hints.get("observed_exceptions"), ("feature", "customer", "plan")),
        [{"name": "entitlement drift review", "owner": "access_owner", "severity": "medium"}],
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": ctx["source"],
        "summary": source_summary(ctx, finding_count=len(findings)),
        "entitlement_scope": section(hints, ("scope", "entitlement_scope"), "FEA", "product_owner", "Audit entitlement scope", evidence_ids, ["customers, plans, roles, and feature flags"]),
        "expected_policy": section(hints, ("expected_policy", "policy"), "FEP", "product_owner", "Confirm expected entitlement policy", evidence_ids, ["source-of-truth entitlement policy"]),
        "observed_exceptions": [
            item("FEF", index, record, "access_owner", evidence_ids, "Resolve entitlement drift finding", name_keys=("name", "feature", "customer", "plan"), extra_keys=("feature", "customer", "plan", "impact"))
            for index, record in enumerate(findings, start=1)
        ],
        "impact_assessment": section(hints, ("impact", "revenue_compliance_impact"), "FEI", "finance_owner", "Assess revenue or compliance impact", evidence_ids, ["revenue leakage and compliance exposure assessment"]),
        "remediation_owners": section(hints, ("remediation", "remediation_owners"), "FER", "access_owner", "Assign entitlement remediation", evidence_ids, ["owner, due date, and correction path"]),
        "customer_communications": section(hints, ("communications", "customer_communications"), "FEC", "customer_success_owner", "Communicate entitlement audit outcome", evidence_ids, ["customer notice or account-team talking points"]),
        "verification": section(hints, ("verification", "verification_checks"), "FEV", "qa_owner", "Verify entitlement correction", evidence_ids, ["post-remediation access and billing verification"]),
        "recurrence_prevention": section(hints, ("prevention", "recurrence_prevention"), "FEX", "product_owner", "Prevent entitlement drift recurrence", evidence_ids, ["policy automation and recurring audit control"]),
        "evidence_references": ctx["evidence_references"],
    }
