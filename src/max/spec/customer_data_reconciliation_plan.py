"""Generate deterministic customer data reconciliation plans."""

from __future__ import annotations

from typing import Any

from max.spec._compact_plan_common import item, named, section
from max.spec._planning_common import compact
from max.spec._review_plan_common import base, source_summary, unique_records

SCHEMA_VERSION = "max.spec.customer_data_reconciliation_plan.v1"
KIND = "max.spec.customer_data_reconciliation_plan"


def generate_customer_data_reconciliation_plan(spec_like: Any) -> dict[str, Any]:
    _spec, ctx, hints, evidence_ids = base(spec_like, "customer_data_reconciliation")
    mismatches = unique_records(named(hints.get("mismatches") or hints.get("mismatch_inventory"), ("id", "name", "field")), [{"name": "customer data reconciliation bootstrap", "severity": "medium"}])
    mismatches = sorted(mismatches, key=lambda row: (_severity(row), compact(row.get("name")).casefold()))
    return {"schema_version": SCHEMA_VERSION, "kind": KIND, "source": ctx["source"], "title": "Customer Data Reconciliation Plan", "summary": source_summary(ctx, mismatch_count=len(mismatches), high_severity_count=sum(1 for row in mismatches if _severity(row) <= 1)), "source_mapping": section(hints, ("source_mapping", "sources", "source_of_truth"), "CDS", "data_owner", "Map customer data source of truth", evidence_ids, ["system, field, owner, source-of-truth rule, downstream consumers, and conflict resolver"]), "mismatch_taxonomy": [item("CDM", i, row, "data_owner", evidence_ids, "Classify customer data mismatch", name_keys=("name", "id", "field"), extra_keys=("severity", "source", "target", "customer_notice")) for i, row in enumerate(mismatches, 1)], "sampling_plan": section(hints, ("sampling_plan", "sampling"), "CDP", "data_owner", "Sample reconciliation records", evidence_ids, ["sample by tenant, field, system pair, severity, and correction path"]), "reconciliation_steps": section(hints, ("reconciliation_steps", "steps"), "CDR", "data_owner", "Run customer data reconciliation", evidence_ids, ["compare systems, confirm source of truth, correct mismatches, and capture before/after evidence"]), "correction_ownership": section(hints, ("correction_ownership", "owners"), "CDO", "data_owner", "Assign customer data correction owner", evidence_ids, ["field owner, system owner, support owner, and approval reviewer"]), "customer_notice_triggers": _notice(mismatches, evidence_ids), "audit_evidence": section(hints, ("audit_evidence", "evidence"), "CDE", "compliance_owner", "Capture customer data reconciliation evidence", evidence_ids, ["diff report, correction log, approvals, notices, and sampled validation results"]), "risk_flags": _flags(hints, mismatches, evidence_ids), "evidence_references": ctx["evidence_references"]}


def _severity(row: dict[str, Any]) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "moderate": 2, "low": 3}.get(compact(row.get("severity")).lower(), 4)


def _notice(mismatches: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    return [item("CDN", i, {"name": compact(row.get("name")), "severity": compact(row.get("severity")) or "medium", "description": "Customer notice required for high-severity or customer-visible data correction." if _severity(row) <= 1 or compact(row.get("customer_notice")).lower() in {"yes", "required"} else "Customer notice not required unless correction changes customer-visible records."}, "customer_owner", evidence_ids, "Evaluate customer notice trigger") for i, row in enumerate(mismatches, 1)]


def _flags(hints: dict[str, Any], mismatches: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    flags = []
    sources = hints.get("source_mapping") or hints.get("sources") or hints.get("source_of_truth")
    if isinstance(sources, list):
        names = [compact(row.get("field")) for row in sources if isinstance(row, dict)]
        if len(names) != len(set(names)):
            flags.append(item("CDF", 1, {"name": "conflicting source of truth", "severity": "high", "description": "Conflicting source-of-truth mappings must be resolved before correction."}, "data_owner", evidence_ids, "Flag reconciliation risk"))
    if any(_severity(row) <= 1 for row in mismatches):
        flags.append(item("CDF", len(flags) + 1, {"name": "high severity mismatch", "severity": "high", "description": "High-severity mismatches require priority correction and customer notice review."}, "data_owner", evidence_ids, "Flag reconciliation risk"))
    return flags or [item("CDF", 1, {"name": "reconciliation inputs ready", "severity": "low"}, "data_owner", evidence_ids, "Record reconciliation readiness")]
